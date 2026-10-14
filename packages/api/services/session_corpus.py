"""Recorded training sessions as training material for the models (ADR-047).

Every training session recorded with the wrist sensors and cameras together, and
cross-checked, is labelled already: the wrist sensors felt each punch (when, which
hand), and the cross-check measured each camera's clock against them (offset and
drift). So the camera punch counter learns from every such session — the punches
moved onto each camera's own clock — besides the research datasets' takes.
Sessions someone labelled by hand (data/labels/{session}.json, with punch types)
also teach the two punch-type models, the cameras' and the wrists'.

Nothing here is a model's own guess: the counter learns from the wrists, the type
models from people's labels. Each session is one group, so cross-validation never
fits on a session and scores on the same one; the datasets' held-out test takes
stay as they are, so the reports remain comparable.
"""

from __future__ import annotations

import json
from collections.abc import Generator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import numpy as np
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from analyze.punch_fusion import redrift, wrist_gaps
from api.services import session_analysis
from contracts import Hand
from store import IMUSampleRow, get_session

LABELS_DIR = Path("data/labels")
POSE_DIR: Path | None = None  # None: where the sessions' pose lands (session_analysis)
TYPES = ("jab", "cross", "hook", "uppercut")
GROUP_PREFIX = "session:"  # a session's group, next to the datasets' take ids


@dataclass
class SessionCamera:
    device: str
    pose_path: Path
    offset_ms: float = 0.0  # camera clock − the wrists' (the session's) clock
    drift: tuple[float, float] | None = None  # (ppm, reference ms)

    def cam_t(self, t_ms: float) -> float:
        """A moment on the session's timeline, on this camera's clock."""
        return redrift(t_ms + self.offset_ms, self.drift)


@dataclass
class SessionMaterial:
    session_id: str
    cameras: list[SessionCamera]
    punches: list[tuple[float, Hand]] = field(default_factory=list)  # (t_ms, hand) the wrists felt
    typed: list[tuple[float, Hand, str]] = field(default_factory=list)  # hand-labelled, with type
    gaps: list[tuple[float, float]] = field(default_factory=list)  # a wrist wasn't streaming

    @property
    def group(self) -> str:
        return f"{GROUP_PREFIX}{self.session_id}"


def is_session(group: str) -> bool:
    return group.startswith(GROUP_PREFIX)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _typed_labels(session_id: str) -> list[tuple[float, Hand, str]]:
    raw = _read(LABELS_DIR / f"{session_id}.json")
    return [
        (float(x["t_ms"]), cast(Hand, x["hand"]), str(x["punch_type"]))
        for x in (raw if isinstance(raw, list) else [])
        if isinstance(x, dict)
        and x.get("hand") in ("left", "right")
        and x.get("punch_type") in TYPES
    ]


def _matched_cameras(sid: str, root: Path, report: dict[str, Any]) -> list[SessionCamera]:
    """The cameras whose clock the cross-check matched to the wrists."""
    out = []
    for c in report.get("cameras") or []:
        pose = root / f"{sid}.{c.get('device_id')}.pose.parquet"
        if c.get("offset_ms") is None or not pose.exists():
            continue
        drift = (
            (float(c["drift_ppm"]), float(c["drift_ref_ms"]))
            if c.get("drift_ppm") is not None and c.get("drift_ref_ms") is not None
            else None
        )
        out.append(SessionCamera(str(c["device_id"]), pose, float(c["offset_ms"]), drift))
    return out


def _gaps(sid: str, report: dict[str, Any]) -> list[tuple[float, float]]:
    """Where either wrist wasn't streaming, on the wrists' clock: no punch there is
    labelled, so none is taught as "no punch". From the cross-check, or worked out
    from the samples for a result saved before it kept them."""
    spans = report.get("wrist_gaps")
    if not isinstance(spans, dict):
        streams = imu_streams(sid)
        ends = [float(t[-1]) for t, _ in streams.values() if len(t)]
        if not ends:
            return []  # the samples aren't here to tell
        spans = wrist_gaps(
            {cast(Hand, h): t.tolist() for h, (t, _) in streams.items()}, 0.0, max(ends)
        )
    return sorted((float(a), float(b)) for hand in spans.values() for a, b in hand)


def sessions(pose_dir: Path | None = None) -> list[SessionMaterial]:
    """Every cross-checked session with wrist punches and a camera whose clock was
    matched to the wrists — the punch counter's material."""
    root = pose_dir or POSE_DIR or session_analysis.POSE_DIR
    out: list[SessionMaterial] = []
    for cache in sorted(root.glob("*.crosscheck.json")):
        sid = cache.name.removesuffix(".crosscheck.json")
        report = _read(cache)
        if not isinstance(report, dict) or not report.get("wrist"):
            continue
        cams = _matched_cameras(sid, root, report)
        punches = [
            (float(p["t_ms"]), cast(Hand, p["hand"]))
            for p in report.get("punches") or []
            if p.get("counted")
            and p.get("peak_g") is not None
            and p.get("hand") in ("left", "right")
        ]
        if cams and punches:
            out.append(SessionMaterial(sid, cams, punches, _typed_labels(sid), _gaps(sid, report)))
    return out


def typed_sessions(pose_dir: Path | None = None) -> list[SessionMaterial]:
    """Every session someone labelled with punch types — the type models' material.
    Its cameras' clocks come from the cross-check when there was one; a camera it
    didn't match is taken as recorded."""
    root = pose_dir or POSE_DIR or session_analysis.POSE_DIR
    out: list[SessionMaterial] = []
    for path in sorted(LABELS_DIR.glob("*.json")):
        sid = path.stem
        typed = _typed_labels(sid)
        if not typed:
            continue
        report = _read(root / f"{sid}.crosscheck.json")
        matched = (
            {c.device: c for c in _matched_cameras(sid, root, report)}
            if isinstance(report, dict)
            else {}
        )
        cams = []
        for pose in sorted(root.glob(f"{sid}.*.pose.parquet")):
            device = pose.name[len(sid) + 1 : -len(".pose.parquet")]
            cams.append(matched.get(device) or SessionCamera(device, pose))
        out.append(SessionMaterial(sid, cams, typed=typed))
    return out


def imu_streams(session_id: str) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Each wrist's samples in the session: times (n,) and ax, ay, az, gx, gy, gz (n, 6)."""
    rows: dict[str, list[tuple[float, ...]]] = {"left": [], "right": []}
    gen: Generator[DBSession, None, None] = get_session()  # type: ignore[assignment]
    try:
        db = next(gen)
        q = select(IMUSampleRow).where(col(IMUSampleRow.session_id) == UUID(session_id))
        for s in db.exec(q.order_by(col(IMUSampleRow.t_ms))):
            h = str(getattr(s.hand, "value", s.hand)).lower()
            if h in rows:
                rows[h].append((s.t_ms, s.ax_g, s.ay_g, s.az_g, s.gx_dps, s.gy_dps, s.gz_dps))
    finally:
        gen.close()
    out = {}
    for h, rr in rows.items():
        a = np.array(rr, dtype=float).reshape(-1, 7)
        out[h] = (a[:, 0], a[:, 1:])
    return out

"""Wrist ↔ camera cross-check of a training session or a dataset take, cached on disk.

Runs `analyze.punch_fusion` over everything a capture recorded: each camera's
pose upload and both wrist sensors' samples. Detection takes a few seconds per
camera-minute, so it runs in a background thread — started when a camera's pose
upload lands, and when a result is asked for that's missing or out of date — and
the result is cached next to the pose:

    data/processed/{session}.crosscheck.json   a training session
    takes/{take}/crosscheck.json               a dataset take

A result carries a signature of its inputs (pose files, wrist samples), so a
late upload makes it stale and it's re-run. A reload of the API drops a run in
progress; the next request starts it again.
"""

from __future__ import annotations

import csv
import datetime
import hashlib
import json
import threading
from collections import Counter
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import numpy as np
from sqlmodel import Session as DBSession
from sqlmodel import col, func, select

from analyze.imu_punches import detect_punches as detect_wrist_punches
from analyze.punch_fusion import WristPunch, camera_punches, cross_check, wrist_gaps
from api.services import dataset_store, session_analysis
from capture.cv.writer import read_pose_parquet
from common import get_logger
from contracts import Hand
from store import FighterRepo, IMUSampleRow, SessionRepo, get_session

log = get_logger(__name__)

Kind = Literal["session", "take"]
Status = Literal["ready", "running", "none"]

VERSION = 1  # bump when the fusion rules change, so old results re-run
DEBOUNCE_S = 8.0  # the cameras' pose uploads land within seconds of each other
BACKGROUND = True  # tests switch the background runs off and call run_now

_lock = threading.Lock()
_timers: dict[tuple[Kind, str], threading.Timer] = {}
_running: set[tuple[Kind, str]] = set()
_again: set[tuple[Kind, str]] = set()
_labels: dict[tuple[Kind, str], dict[str, str]] = {}


@dataclass
class _Inputs:
    pose: dict[str, Path]  # device id → its pose parquet
    signature: str
    folder: Path | None  # the take's folder; None for a session


@contextmanager
def _db(db: DBSession | None) -> Iterator[DBSession]:
    if db is not None:
        yield db
        return
    gen: Generator[DBSession, None, None] = get_session()  # type: ignore[assignment]
    try:
        yield next(gen)
    finally:
        gen.close()


def _sig(*parts: object) -> str:
    return hashlib.sha1(json.dumps([VERSION, *parts], default=str).encode()).hexdigest()[:16]


def _stat(p: Path) -> tuple[str, int, int]:
    st = p.stat()
    return (p.name, st.st_size, st.st_mtime_ns)


def _inputs(kind: Kind, capture_id: UUID, db: DBSession) -> _Inputs | None:
    """What a cross-check would read, or None when there's no camera pose to check."""
    if kind == "take":
        folder = dataset_store.take_dir(capture_id)
        if folder is None:
            return None
        pose = {p.stem: p for p in sorted((folder / "pose").glob("*.parquet"))}
        imu = folder / "imu.csv"
        imu_sig: object = _stat(imu) if imu.exists() else None
        duration = dataset_store.read_take_json(folder).get("duration_ms")
    else:
        folder = None
        prefix, suffix = f"{capture_id}.", ".pose.parquet"
        pose = {
            p.name[len(prefix) : -len(suffix)]: p for p in session_analysis.pose_files(capture_id)
        }
        imu_sig = tuple(
            db.exec(
                select(func.count(), func.max(IMUSampleRow.t_ms)).where(
                    IMUSampleRow.session_id == capture_id
                )
            ).one()
        )
        row = SessionRepo(db).get(capture_id)
        duration = row.duration_ms if row else None
    if not pose:
        return None
    return _Inputs(
        pose=pose,
        signature=_sig([_stat(p) for p in pose.values()], imu_sig, duration),
        folder=folder,
    )


def _cache_path(kind: Kind, capture_id: UUID, folder: Path | None) -> Path:
    if kind == "take" and folder is not None:
        return folder / "crosscheck.json"
    return session_analysis.POSE_DIR / f"{capture_id}.crosscheck.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    try:
        data: dict[str, Any] = json.loads(path.read_text())
        return data
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# Running it
# --------------------------------------------------------------------------


def _wrist_samples(
    kind: Kind, capture_id: UUID, folder: Path | None, db: DBSession
) -> dict[Hand, np.ndarray]:
    """Each wrist's samples as an (n, 4) array of t_ms, ax, ay, az (g)."""
    rows: dict[str, list[tuple[float, float, float, float]]] = {"left": [], "right": []}
    if folder is not None:
        try:
            with (folder / "imu.csv").open(newline="") as f:
                for r in csv.DictReader(f):
                    hand = r.get("hand", "")
                    if hand in rows:
                        rows[hand].append(
                            (float(r["t_ms"]), float(r["ax_g"]), float(r["ay_g"]), float(r["az_g"]))
                        )
        except (OSError, ValueError, KeyError):
            pass
    else:
        q = select(IMUSampleRow).where(IMUSampleRow.session_id == capture_id)
        for s in db.exec(q.order_by(col(IMUSampleRow.t_ms))):
            h = str(getattr(s.hand, "value", s.hand)).lower()
            if h in rows:
                rows[h].append((s.t_ms, s.ax_g, s.ay_g, s.az_g))
    return {
        "left": np.array(sorted(rows["left"]), dtype=float).reshape(-1, 4),
        "right": np.array(sorted(rows["right"]), dtype=float).reshape(-1, 4),
    }


def run_now(
    kind: Kind,
    capture_id: UUID,
    *,
    labels: dict[str, str] | None = None,
    db: DBSession | None = None,
) -> dict[str, Any] | None:
    """Cross-check the capture now and cache the result (None: no camera pose)."""
    with _db(db) as s:
        inp = _inputs(kind, capture_id, s)
        if inp is None:
            return None
        if inp.folder is not None:
            take = dataset_store.read_take_json(inp.folder)
            stance, duration = take.get("stance"), take.get("duration_ms")
            labels = {**_take_labels(inp.folder), **(labels or {})}
        else:
            row = SessionRepo(s).get(capture_id)
            fighter = FighterRepo(s).get(row.fighter_id) if row else None
            stance = str(fighter.stance) if fighter and fighter.stance else None
            duration = row.duration_ms if row else None
        samples = _wrist_samples(kind, capture_id, inp.folder, s)

    wrist: list[WristPunch] = []
    for hand, a in samples.items():
        if len(a) >= 20:
            wrist += [
                WristPunch(e.t_ms, hand, e.peak_g)
                for e in detect_wrist_punches(a[:, 0], a[:, 1], a[:, 2], a[:, 3])
            ]
    per_camera = {}
    for dev, path in inp.pose.items():
        frames = read_pose_parquet(path)
        if frames:
            per_camera[dev] = camera_punches(frames, stance=stance)
    has_wrist = any(len(a) for a in samples.values())
    end = float(duration or max((float(a[-1, 0]) for a in samples.values() if len(a)), default=0.0))
    gaps = (
        wrist_gaps({h: a[:, 0].tolist() for h, a in samples.items()}, 0.0, end)
        if has_wrist
        else None
    )
    cc = cross_check(wrist, per_camera, gaps=gaps)

    by = Counter((p.source, p.counted) for p in cc.punches)
    counted = cc.counted
    labels = labels or {}
    report: dict[str, Any] = {
        "version": VERSION,
        "signature": inp.signature,
        "computed_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "wrist": has_wrist,
        "hands": cc.hands,
        "hands_swapped": cc.hands_swapped,
        "totals": {
            "counted": len(counted),
            "confirmed": by[("both", True)],
            "wrist_only": by[("wrist", True)],
            "camera_only": by[("camera", True)],
            "unconfirmed": by[("camera", False)],
            "wrist": cc.wrist_punches,
            "camera": cc.camera_punches,
        },
        # Share of the counted punches both sides saw.
        "agreement": (
            round(by[("both", True)] / len(counted), 2)
            if counted and has_wrist and per_camera
            else None
        ),
        "cameras": [
            {
                "device_id": r.device,
                "label": labels.get(r.device),
                "punches": r.punches,
                "offset_ms": r.offset_ms,
                "agreement": r.agreement,
                "coverage": r.coverage,
                "hands": r.hands,
            }
            for r in cc.cameras
        ],
        "punches": [
            {
                "t_ms": round(p.t_ms, 1),
                "hand": p.hand,
                "source": p.source,
                "counted": p.counted,
                "peak_g": p.peak_g,
                "speed_ms": p.speed_ms,
                "cameras": len(p.cameras),
            }
            for p in cc.punches
        ],
    }
    path = _cache_path(kind, capture_id, inp.folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(report))
    tmp.replace(path)
    log.info(
        "crosscheck.done",
        extra={
            "_ctx_capture_id": str(capture_id),
            "_ctx_counted": len(counted),
            "_ctx_agreement": report["agreement"],
            "_ctx_hands": cc.hands,
        },
    )
    return report


def _take_labels(folder: Path) -> dict[str, str]:
    """Camera names saved next to a take's clips."""
    out: dict[str, str] = {}
    for p in (folder / "video").glob("*.json"):
        try:
            label = json.loads(p.read_text()).get("label")
        except (OSError, ValueError, AttributeError):
            continue
        if label:
            out[p.stem] = str(label)
    return out


def _run(key: tuple[Kind, str]) -> None:
    with _lock:
        _timers.pop(key, None)
        if key in _running:
            _again.add(key)
            return
        _running.add(key)
        labels = _labels.get(key)
    try:
        run_now(key[0], UUID(key[1]), labels=labels)
    except Exception:
        log.exception("crosscheck.failed", extra={"_ctx_capture_id": key[1]})
    finally:
        with _lock:
            _running.discard(key)
            again = key in _again
            _again.discard(key)
    if again:
        schedule(key[0], UUID(key[1]), delay_s=1.0)


def schedule(
    kind: Kind,
    capture_id: UUID,
    *,
    labels: dict[str, str] | None = None,
    delay_s: float = DEBOUNCE_S,
) -> None:
    """Cross-check in the background after `delay_s` (restarted by a newer call)."""
    if not BACKGROUND:
        return
    key: tuple[Kind, str] = (kind, str(capture_id))
    with _lock:
        if labels:
            _labels[key] = labels
        old = _timers.pop(key, None)
        if old is not None:
            old.cancel()
        if key in _running:
            _again.add(key)  # inputs changed mid-run: go again when it ends
            return
        timer = threading.Timer(delay_s, _run, args=(key,))
        timer.daemon = True
        _timers[key] = timer
        timer.start()


def result(
    kind: Kind,
    capture_id: UUID,
    *,
    db: DBSession | None = None,
    labels: dict[str, str] | None = None,
) -> tuple[Status, dict[str, Any] | None]:
    """The capture's cross-check: ("ready", result), ("running", None) while one
    is being made — started here when it's missing or stale — or ("none", None)
    when no camera pose was uploaded."""
    with _db(db) as s:
        inp = _inputs(kind, capture_id, s)
    if inp is None:
        return "none", None
    cached = _read_cache(_cache_path(kind, capture_id, inp.folder))
    if cached is not None and cached.get("signature") == inp.signature:
        return "ready", cached
    key: tuple[Kind, str] = (kind, str(capture_id))
    with _lock:
        busy = key in _timers or key in _running
    if not busy:
        schedule(kind, capture_id, labels=labels, delay_s=0.0)
    return "running", None

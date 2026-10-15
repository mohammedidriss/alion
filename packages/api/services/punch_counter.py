"""The camera punch counter in use (ADR-059).

The newest trained counter (`training`, ADR-019: learnt from the datasets'
takes, the wrist sensors as the answer key) counts the cameras' punches after a
recording — in every cross-check — when there is one; the hand-written detector
(`punch_fusion.camera_punches`, ADR-009) when there isn't, or the model can't
run. On the Single round dataset (15 Oct 2026) the trained counter's precision
was 0.79 to the detector's 0.27, with 32 punches counted on the hand that wasn't
punching to the detector's 543.

Live, in the browser, the cameras still run the detector; the live count comes
from the wrist sensors when they're on (ADR-059).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from analyze import punch_model
from analyze.punch_fusion import camera_punches as heuristic_punches
from common import get_logger
from contracts import Hand, PoseFrame, PunchEvent

log = get_logger(__name__)

MODELS_DIR = Path("data/ml/punch_counter")  # training.MODELS_DIR: one folder per dataset
SPEED_WINDOW_MS = 150.0  # the wrist's peak speed this close to the punch

_lock = threading.Lock()
_cache: dict[str, Any] = {}


def _newest() -> Path | None:
    files = [p for p in MODELS_DIR.glob("*/v*.joblib") if p.with_suffix(".json").exists()]
    return max(files, key=lambda p: p.stat().st_mtime) if files else None


def current() -> dict[str, Any] | None:
    """The trained counter in use — the most recently trained — or None:
    {model, threshold, label, dataset_id, version, report}."""
    path = _newest()
    if path is None:
        return None
    key = f"{path}:{path.stat().st_mtime}"
    with _lock:
        if _cache.get("key") == key:
            return _cache["value"]  # type: ignore[no-any-return]
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]

    try:
        saved = joblib.load(path)
        report = json.loads(path.with_suffix(".json").read_text())
    except Exception:  # an unreadable file: count with the detector
        log.exception("punch_counter.unreadable", extra={"_ctx_path": str(path)})
        return None
    value = {
        "model": saved["model"],
        "threshold": float(saved["threshold"]),
        "dataset_id": path.parent.name,
        "version": int(path.stem[1:]),
        "label": f"{path.parent.name[:8]}/v{path.stem[1:]}",
        "report": report,
    }
    with _lock:
        _cache.update(key=key, value=value)
    return value


def label() -> str | None:
    """What counts the cameras' punches: a trained counter's label, or None (the
    detector) — part of a cross-check's signature, so a new counter re-runs them."""
    cur = current()
    return cur["label"] if cur else None


def _lead(hand: Hand, stance: str | None) -> Any:
    if stance == "orthodox":
        return "lead" if hand == "left" else "rear"
    if stance == "southpaw":
        return "lead" if hand == "right" else "rear"
    return None


def _speed(tr: punch_model.Track, t_ms: float, hand: Hand) -> float:
    """The wrist's peak speed (m/s, world landmarks) within ±150 ms of the punch."""
    wrist = 15 if hand == "left" else 16
    near = np.flatnonzero(np.abs(tr.t - t_ms) <= SPEED_WINDOW_MS)
    if len(near) < 2:
        return 0.0
    i0, i1 = max(int(near[0]) - 1, 0), int(near[-1])
    xyz = tr.world[i0 : i1 + 1, wrist, :]
    dt = np.diff(tr.t[i0 : i1 + 1]) / 1000.0
    step = np.linalg.norm(np.diff(xyz, axis=0), axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        v = step / dt
    v = v[np.isfinite(v)]
    return round(float(v.max()), 2) if len(v) else 0.0


def camera_punches(frames: list[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
    """One camera's punches, by the counter in use."""
    cur = current()
    if cur is None or len(frames) < 30:
        return heuristic_punches(frames, stance=stance)
    try:
        tr = punch_model.track(frames)
        found = punch_model.events(punch_model.probabilities(cur["model"], tr), cur["threshold"])
    except Exception:  # the model can't run on this pose: the detector counts instead
        log.exception("punch_counter.failed")
        return heuristic_punches(frames, stance=stance)
    sid: UUID = frames[0].session_id
    return [
        PunchEvent(
            session_id=sid,
            t_ms=max(0.0, float(t)),
            hand=h,
            lead_or_rear=_lead(h, stance),
            velocity_ms=_speed(tr, float(t), h),
            velocity_source="world",
            detected_by="custom_ml",
            confidence=min(1.0, max(0.0, float(p))),
        )
        for t, h, p in found
    ]

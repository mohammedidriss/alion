"""Punch events for a multi-camera training session, from its cameras' pose.

The browser cameras run pose and count punches live, but only upload their pose
stream (`data/processed/{session}.{device}.pose.parquet`) and clip at Stop — the
punch events the per-round breakdown, speed and score are built from were never
stored for multi-camera sessions. This runs the server-side detector (the one the
single-camera capture used) over the main camera's pose and stores its events.

Main camera: the laptop (the front view the heuristic is tuned for) when its
label is known, else the camera with the most frames that see both wrists.
Re-running replaces the session's events, so it's safe to call again (e.g. when a
camera's pose upload lands after Stop).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from sqlmodel import Session as DBSession
from sqlmodel import delete

from analyze import classify_punch_type, detect_punches
from capture.cv.writer import read_pose_parquet
from common import get_logger
from contracts import PoseFrame
from store import (
    DetectionSourceEnum,
    FighterRepo,
    HandEnum,
    LeadOrRearEnum,
    PunchEventRepo,
    PunchEventRow,
    PunchTypeEnum,
    SessionRepo,
    VelocitySourceEnum,
)

log = get_logger(__name__)

POSE_DIR = Path("data/processed")
_HISTORY_MS = 1000.0  # pose window before a punch for its type
_WRIST_L, _WRIST_R = 15, 16


def pose_files(session_id: UUID) -> list[Path]:
    """Each camera's pose upload for the session."""
    return sorted(POSE_DIR.glob(f"{session_id}.*.pose.parquet"))


def _device_of(path: Path, session_id: UUID) -> str:
    return path.name[len(f"{session_id}.") : -len(".pose.parquet")]


def _coverage(frames: list[PoseFrame]) -> int:
    """Frames where both wrists are confidently seen — a camera's usefulness."""
    return sum(
        1
        for f in frames
        if f.landmarks[_WRIST_L].visibility >= 0.5 and f.landmarks[_WRIST_R].visibility >= 0.5
    )


def pick_main_camera(
    session_id: UUID, labels: dict[str, str]
) -> tuple[str, list[PoseFrame]] | None:
    """(device id, frames) of the camera to detect punches from, or None."""
    loaded = {_device_of(p, session_id): read_pose_parquet(p) for p in pose_files(session_id)}
    loaded = {d: f for d, f in loaded.items() if f}
    if not loaded:
        return None
    laptops = [d for d in loaded if labels.get(d, "").lower() == "laptop"]
    device = laptops[0] if laptops else max(loaded, key=lambda d: _coverage(loaded[d]))
    return device, loaded[device]


def analyze(session_id: UUID, db: DBSession, labels: dict[str, str] | None = None) -> int:
    """Detect the session's punches from its main camera's pose and store them
    (replacing earlier ones). Returns how many were stored."""
    sessions = SessionRepo(db)
    row = sessions.get(session_id)
    if row is None:
        return 0
    picked = pick_main_camera(session_id, labels or {})
    if picked is None:
        return 0
    device, frames = picked
    fighter = FighterRepo(db).get(row.fighter_id)
    stance = str(fighter.stance) if fighter and fighter.stance else None

    events = detect_punches(frames, stance=stance)
    out: list[PunchEventRow] = []
    for ev in events:
        history = [f for f in frames if ev.t_ms - _HISTORY_MS <= f.t_ms <= ev.t_ms]
        ptype = classify_punch_type(history, ev.hand, stance) if history else None
        out.append(
            PunchEventRow(
                session_id=session_id,
                t_ms=ev.t_ms,
                hand=HandEnum(ev.hand),
                lead_or_rear=LeadOrRearEnum(ev.lead_or_rear) if ev.lead_or_rear else None,
                velocity_ms=round(ev.velocity_ms, 2),
                velocity_source=VelocitySourceEnum(ev.velocity_source),
                punch_type=PunchTypeEnum(ptype) if ptype else None,
                detected_by=DetectionSourceEnum(ev.detected_by),
                confidence=ev.confidence,
            )
        )
    db.exec(delete(PunchEventRow).where(PunchEventRow.session_id == session_id))  # type: ignore[arg-type]
    db.commit()
    if out:
        PunchEventRepo(db).add_many(out)
    sessions.attach_artifacts(
        session_id,
        pose_parquet_path=str(POSE_DIR / f"{session_id}.{device}.pose.parquet"),
        frame_count=len(frames),
    )
    log.info(
        "session.analyzed",
        extra={"_ctx_session_id": str(session_id), "_ctx_device": device, "_ctx_events": len(out)},
    )
    return len(out)


def clip_labels(video_dir: Path, session_id: UUID) -> dict[str, str]:
    """Device labels saved next to the clips (so a late analysis still knows the laptop)."""
    out: dict[str, str] = {}
    for p in video_dir.glob(f"{session_id}.*.json"):
        try:
            label = json.loads(p.read_text()).get("label")
        except (OSError, ValueError):
            continue
        if label:
            out[p.name[len(f"{session_id}.") : -len(".json")]] = str(label)
    return out

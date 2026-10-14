"""What the body sensors recorded in each of a fighter's sessions.

The HRV and IMU tabs list every session — not only the few with a resting
baseline — with what the Polar strap and the wrist sensors stored in it, or
nothing, so a missing recording is plain to see. The summaries come from
`services.sensor_summary` (one grouped query per sensor).

Fighter-scoped, so the access guard asks for this fighter's training data
(ADR-017).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import select

from api.deps import db_session
from api.routes.auth import require_current_user
from api.routes.sessions import _recorded
from api.services import sensor_summary
from store import Fighter
from store import Session as SessionRow
from store.models import UtcDatetime

router = APIRouter(
    prefix="/fighters",
    tags=["recordings"],
    dependencies=[Depends(require_current_user)],
)


class HeartRecording(BaseModel):
    beats: int
    duration_s: float
    mean_hr_bpm: float | None  # None when no interval is a plausible heartbeat
    max_hr_bpm: float | None
    rmssd_ms: float | None  # None below two plausible beats
    sdnn_ms: float | None


class WristRecording(BaseModel):
    samples: int
    duration_s: float
    hz: float | None
    peak_g: float  # the largest acceleration magnitude stored


class SessionRecordings(BaseModel):
    session_id: UUID
    started_at: UtcDatetime | None  # ISO with +00:00, like the session list
    status: str
    duration_s: float | None  # the session's own length, when it has ended
    baseline_rmssd_ms: float | None  # the resting baseline, when one was recorded
    heart: HeartRecording | None  # None: the strap stored nothing
    wrists: dict[str, WristRecording]  # "left" / "right" ("unknown" for unlabelled rows)


@router.get("/{fighter_id}/recordings", response_model=list[SessionRecordings])
def fighter_recordings(
    fighter_id: UUID, db: DBSession = Depends(db_session)
) -> list[SessionRecordings]:
    """Every recorded session of this fighter, newest first, with what the heart-rate
    strap and the wrist sensors stored in it. A session counts as recorded when the
    cameras recorded it or a sensor stored something."""
    if db.get(Fighter, fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    sessions = list(db.exec(select(SessionRow).where(SessionRow.fighter_id == fighter_id)).all())
    ids = [s.id for s in sessions]
    if not ids:
        return []

    beats = sensor_summary.heart_by_session(db, ids)
    wrists = sensor_summary.wrists_by_session(db, ids)

    recorded = {s.id for s in _recorded(sessions)}
    shown = [s for s in sessions if s.id in recorded or s.id in beats or s.id in wrists]
    shown.sort(key=lambda s: s.started_at or datetime.min, reverse=True)
    return [
        SessionRecordings(
            session_id=s.id,
            started_at=s.started_at,
            status=s.status.value if hasattr(s.status, "value") else str(s.status),
            duration_s=(
                round((s.ended_at - s.started_at).total_seconds(), 1)
                if s.started_at and s.ended_at
                else None
            ),
            baseline_rmssd_ms=s.baseline_rmssd_ms,
            heart=HeartRecording(**asdict(beats[s.id])) if s.id in beats else None,
            wrists={k: WristRecording(**asdict(w)) for k, w in wrists.get(s.id, {}).items()},
        )
        for s in shown
    ]

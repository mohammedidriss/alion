"""What the body sensors recorded in each of a fighter's sessions.

The HRV and IMU tabs list every session — not only the few with a resting
baseline — with what the Polar strap and the wrist sensors stored in it, or
nothing, so a missing recording is plain to see. One query per sensor, grouped
by session; RMSSD and SDNN come from `analyze.hrv_metrics` over the session's
beat-to-beat intervals.

Fighter-scoped, so the access guard asks for this fighter's training data
(ADR-017).
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from analyze.hrv_metrics import mean_hr_bpm, rmssd_ms, sdnn_ms
from api.deps import db_session
from api.routes.auth import require_current_user
from api.routes.sessions import _recorded
from contracts import HRSample
from store import Fighter, HRSampleRow, IMUSampleRow
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


# Beat-to-beat intervals outside 30–200 bpm are dropouts or noise, not heartbeats;
# one of them would swamp RMSSD (a gap of a few seconds reads as thousands of ms).
_RR_MIN_MS, _RR_MAX_MS = 300.0, 2000.0


def _heart(rows: list[tuple[float, float, float]]) -> HeartRecording:
    """A session's beats, in time order: (t_ms, rr_ms, hr_bpm). The rates and
    variability use the plausible intervals only."""
    beats = [
        HRSample(session_id=UUID(int=0), t_ms=t, rr_ms=rr, hr_bpm=hr)
        for t, rr, hr in rows
        if _RR_MIN_MS <= rr <= _RR_MAX_MS
    ]
    two = len(beats) >= 2
    return HeartRecording(
        beats=len(rows),
        duration_s=round((rows[-1][0] - rows[0][0]) / 1000.0, 1),
        mean_hr_bpm=round(mean_hr_bpm(beats), 1) if beats else None,
        max_hr_bpm=round(max(b.hr_bpm for b in beats), 1) if beats else None,
        rmssd_ms=round(rmssd_ms(beats), 1) if two else None,
        sdnn_ms=round(sdnn_ms(beats), 1) if two else None,
    )


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

    beats: dict[UUID, list[tuple[float, float, float]]] = defaultdict(list)
    for sid, t, rr, hr in db.exec(
        select(HRSampleRow.session_id, HRSampleRow.t_ms, HRSampleRow.rr_ms, HRSampleRow.hr_bpm)
        .where(col(HRSampleRow.session_id).in_(ids))
        .order_by(col(HRSampleRow.session_id), col(HRSampleRow.t_ms))
    ).all():
        beats[sid].append((t, rr, hr))

    wrists: dict[UUID, dict[str, WristRecording]] = defaultdict(dict)
    ax, ay, az = col(IMUSampleRow.ax_g), col(IMUSampleRow.ay_g), col(IMUSampleRow.az_g)
    t_ms = col(IMUSampleRow.t_ms)
    # Grouped in the database — a session holds ~100 rows a second per wrist.
    for sid, hand, n, t0, t1, peak2 in db.execute(
        sa_select(
            col(IMUSampleRow.session_id),
            col(IMUSampleRow.hand),
            func.count(),
            func.min(t_ms),
            func.max(t_ms),
            func.max(ax * ax + ay * ay + az * az),
        )
        .where(col(IMUSampleRow.session_id).in_(ids))
        .group_by(col(IMUSampleRow.session_id), col(IMUSampleRow.hand))
    ).all():
        span_s = (t1 - t0) / 1000.0
        wrists[sid][str(getattr(hand, "value", hand)) if hand is not None else "unknown"] = (
            WristRecording(
                samples=n,
                duration_s=round(span_s, 1),
                hz=round((n - 1) / span_s, 1) if n > 1 and span_s > 0 else None,
                peak_g=round(math.sqrt(peak2), 2),
            )
        )

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
            heart=_heart(beats[s.id]) if beats.get(s.id) else None,
            wrists=wrists.get(s.id, {}),
        )
        for s in shown
    ]

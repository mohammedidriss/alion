"""Live reader — one poll for the session page's watch-style heart + wrist readout.

Combines the Polar H10 stream (latest beats, rolling HRV, heart-rate zone) with
the wrist IMUs (per-wrist g trace) so the reader polls a single endpoint twice
a second instead of four.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.deps import db_session, fighter_repo, session_repo
from api.routes.auth import require_current_user
from api.routes.imu_ble import ImuBleStatus, session_status
from api.services import hrv_runner
from store import FighterRepo, HRSampleRow, SessionRepo

router = APIRouter(prefix="/sessions", tags=["live"], dependencies=[Depends(require_current_user)])

BEATS = 60  # recent beats returned for the HR line


class LiveHeart(BaseModel):
    streaming: bool
    bpm: float | None = None  # latest beat
    bpm_trace: list[float] = []  # last BEATS beats, oldest first
    rmssd_ms: float | None = None  # rolling window (hrv_runner)
    max_hr: int | None = None  # age-predicted; None without a date of birth
    zone: int | None = None  # 1–5 by % of max_hr; 0 = below zone 1
    error: str | None = None  # why the strap's stream failed, e.g. "not found"


class LiveOut(BaseModel):
    heart: LiveHeart
    imu: ImuBleStatus


def max_hr_for(dob: date | None, today: date | None = None) -> int | None:
    """Age-predicted max HR, Tanaka et al. 2001: 208 − 0.7 × age."""
    if dob is None:
        return None
    today = today or date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return round(208 - 0.7 * age) if 5 <= age <= 100 else None


def hr_zone(bpm: float, max_hr: int) -> int:
    """Five-zone model by % of max HR: <50 % → 0, 50–60 → 1, … , ≥90 → 5."""
    pct = 100.0 * bpm / max_hr  # whole percents: (0.7 − 0.5) · 10 is 1.999… in floats
    return 0 if pct < 50 else min(5, int(pct // 10) - 4)


@router.get("/{session_id}/live", response_model=LiveOut)
def live(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    fighters: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> LiveOut:
    session = sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    rows = db.exec(
        select(HRSampleRow)
        .where(HRSampleRow.session_id == session_id)
        .order_by(col(HRSampleRow.t_ms).desc())
        .limit(BEATS)
    ).all()
    trace = [round(r.hr_bpm, 1) for r in reversed(rows)]
    metrics = hrv_runner.latest_metrics(session_id)
    fighter = fighters.get(session.fighter_id) if session.fighter_id else None
    max_hr = max_hr_for(fighter.dob if fighter else None)
    bpm = trace[-1] if trace else None
    heart = LiveHeart(
        streaming=hrv_runner.is_running(session_id),
        bpm=bpm,
        bpm_trace=trace,
        rmssd_ms=round(metrics.rmssd_ms, 1) if metrics else None,
        max_hr=max_hr,
        zone=hr_zone(bpm, max_hr) if bpm is not None and max_hr else None,
        error=hrv_runner.last_error(session_id),
    )
    return LiveOut(heart=heart, imu=session_status(session_id))

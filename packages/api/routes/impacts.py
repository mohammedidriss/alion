"""Head-impact (instrumented mouthguard) upload + listing (ADR 007).

Composition-root wiring for the `capture/mouthguard` adapter. Until the device
is in hand, rows are populated by a CSV upload replayed through the adapter's
parser (ADR 002 — synthetic/self-test data only until Phase 8).

A head impact is a received head event, distinct from a thrown punch — its own
table, never merged into punch_event. Advisory telemetry only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import head_impact_repo, session_repo
from api.routes.auth import require_current_user
from capture.mouthguard import parse_impacts_text
from store import (
    HeadImpactEventRead,
    HeadImpactEventRow,
    HeadImpactRepo,
    ImpactLocationEnum,
    SessionRepo,
)

router = APIRouter(
    prefix="/sessions",
    tags=["impacts"],
    dependencies=[Depends(require_current_user)],
)

# Impacts are sparse (a handful per round), so a small cap is generous.
_MAX_IMPACTS_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


@router.post("/{session_id}/impacts/upload", response_model=int)
async def upload_impacts_csv(
    session_id: UUID,
    file: UploadFile = File(...),
    sessions: SessionRepo = Depends(session_repo),
    impacts: HeadImpactRepo = Depends(head_impact_repo),
) -> int:
    """Upload a head-impact CSV; replaces any prior impacts for the session."""
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    data = await file.read(_MAX_IMPACTS_UPLOAD_BYTES + 1)
    if len(data) > _MAX_IMPACTS_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"impacts CSV exceeds the {_MAX_IMPACTS_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    try:
        parsed = parse_impacts_text(data.decode("utf-8", errors="ignore"))
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    rows = [
        HeadImpactEventRow(
            session_id=session_id,
            t_ms=t_ms,
            peak_linear_accel_g=r.peak_linear_accel_g,
            peak_rotational_vel_rad_s=r.peak_rotational_vel_rad_s,
            peak_rotational_accel_rad_s2=r.peak_rotational_accel_rad_s2,
            location=ImpactLocationEnum(r.location),
            device_id=r.device_id,
            confidence=r.confidence,
        )
        for t_ms, r in parsed
    ]
    return impacts.replace_for_session(session_id, rows)


@router.get("/{session_id}/impacts", response_model=list[HeadImpactEventRead])
def list_impacts(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    impacts: HeadImpactRepo = Depends(head_impact_repo),
) -> list[HeadImpactEventRead]:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [
        HeadImpactEventRead(
            session_id=r.session_id,
            t_ms=r.t_ms,
            peak_linear_accel_g=r.peak_linear_accel_g,
            peak_rotational_vel_rad_s=r.peak_rotational_vel_rad_s,
            peak_rotational_accel_rad_s2=r.peak_rotational_accel_rad_s2,
            location=r.location,
            device_id=r.device_id,
            confidence=r.confidence,
        )
        for r in impacts.list_for_session(session_id)
    ]

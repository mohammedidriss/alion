"""RQ1 study endpoints — rater-score storage + bulk read.

Pairs with the dashboard `RQ1RaterCard`. Ratings live in the
`rq1_rating` table so the study can pool data across raters and
machines. The advice generations they're rating live in
`coach_advice_cache` (filled by the `/sessions/{id}/advice` route).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select as _select

from api.deps import db_session, session_repo
from store import (
    PayloadModeEnum,
    RaterScoreRead,
    RaterScoreRow,
    SessionRepo,
)

router = APIRouter(prefix="/studies/rq1", tags=["studies"])


class RatingUpsertRequest(BaseModel):
    """One Likert score for one (rater, session, mode, criterion) tuple."""

    payload_mode: PayloadModeEnum
    rater_id: str = Field(min_length=1, max_length=80)
    criterion: str = Field(min_length=1, max_length=40)
    score: int = Field(ge=1, le=5)
    notes: str | None = None


@router.post("/sessions/{session_id}/ratings", response_model=RaterScoreRead)
def upsert_rating(
    session_id: UUID,
    body: RatingUpsertRequest,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> RaterScoreRead:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    stmt = _select(RaterScoreRow).where(
        RaterScoreRow.session_id == session_id,  # type: ignore[arg-type]
        RaterScoreRow.payload_mode == body.payload_mode,  # type: ignore[arg-type]
        RaterScoreRow.rater_id == body.rater_id,  # type: ignore[arg-type]
        RaterScoreRow.criterion == body.criterion,  # type: ignore[arg-type]
    )
    existing = db.exec(stmt).first()
    if existing is not None:
        existing.score = body.score
        existing.notes = body.notes
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return RaterScoreRead.model_validate(existing, from_attributes=True)

    row = RaterScoreRow(
        session_id=session_id,
        payload_mode=body.payload_mode,
        rater_id=body.rater_id,
        criterion=body.criterion,
        score=body.score,
        notes=body.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return RaterScoreRead.model_validate(row, from_attributes=True)


@router.get(
    "/sessions/{session_id}/ratings",
    response_model=list[RaterScoreRead],
)
def list_ratings_for_session(
    session_id: UUID,
    rater_id: str | None = None,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> list[RaterScoreRead]:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    stmt = _select(RaterScoreRow).where(
        RaterScoreRow.session_id == session_id  # type: ignore[arg-type]
    )
    if rater_id:
        stmt = stmt.where(RaterScoreRow.rater_id == rater_id)  # type: ignore[arg-type]
    rows = list(db.exec(stmt).all())
    return [RaterScoreRead.model_validate(r, from_attributes=True) for r in rows]


@router.get("/ratings", response_model=list[RaterScoreRead])
def list_all_ratings(
    rater_id: str | None = None,
    db: DBSession = Depends(db_session),
) -> list[RaterScoreRead]:
    """Bulk read for the aggregation script."""
    stmt = _select(RaterScoreRow)
    if rater_id:
        stmt = stmt.where(RaterScoreRow.rater_id == rater_id)  # type: ignore[arg-type]
    rows = list(db.exec(stmt).all())
    return [RaterScoreRead.model_validate(r, from_attributes=True) for r in rows]

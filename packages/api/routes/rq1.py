"""RQ1 study endpoints — rater-score storage + bulk read.

Pairs with the dashboard `RQ1RaterCard`. Ratings live in the
`rq1_rating` table so the study can pool data across raters and
machines. The advice generations they're rating live in
`coach_advice_cache` (filled by the `/sessions/{id}/advice` route).

Each score belongs to the signed-in rater, under a code made from their account
("R-" + the start of its id), never a typed name another rater could reuse; a
changed score is a new row and the old one is kept (ADR-036).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import col
from sqlmodel import select as _select

from api.access import Viewer, require_researcher, require_viewer
from api.deps import db_session, session_repo
from api.routes.auth import require_current_user
from store import (
    PayloadModeEnum,
    RaterScoreRead,
    RaterScoreRow,
    SessionRepo,
    User,
)

router = APIRouter(
    prefix="/studies/rq1",
    tags=["studies"],
    dependencies=[Depends(require_current_user)],
)


def rater_code(user: User) -> str:
    """The rater's code in every export: stable, and not their name or email."""
    return f"R-{user.id.hex[:8]}"


class RatingUpsertRequest(BaseModel):
    """One Likert score for one (session, mode, criterion), from the signed-in rater."""

    payload_mode: PayloadModeEnum
    criterion: str = Field(min_length=1, max_length=40)
    score: int = Field(ge=1, le=5)
    notes: str | None = None


class RaterMe(BaseModel):
    rater_id: str


@router.get("/me", response_model=RaterMe)
def me(viewer: Viewer = Depends(require_viewer)) -> RaterMe:
    return RaterMe(rater_id=rater_code(viewer.user))


@router.post("/sessions/{session_id}/ratings", response_model=RaterScoreRead)
def upsert_rating(
    session_id: UUID,
    body: RatingUpsertRequest,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
    viewer: Viewer = Depends(require_viewer),
) -> RaterScoreRead:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    current = db.exec(
        _select(RaterScoreRow).where(
            RaterScoreRow.session_id == session_id,
            RaterScoreRow.payload_mode == body.payload_mode,
            RaterScoreRow.user_id == viewer.user.id,
            RaterScoreRow.criterion == body.criterion,
            col(RaterScoreRow.superseded_at).is_(None),
        )
    ).first()
    if current is not None:
        if current.score == body.score and current.notes == body.notes:
            return RaterScoreRead.model_validate(current, from_attributes=True)
        current.superseded_at = datetime.now(UTC)
        db.add(current)

    row = RaterScoreRow(
        session_id=session_id,
        payload_mode=body.payload_mode,
        rater_id=rater_code(viewer.user),
        user_id=viewer.user.id,
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
def list_my_ratings_for_session(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
    viewer: Viewer = Depends(require_viewer),
) -> list[RaterScoreRead]:
    """The signed-in rater's current scores for this session — never another
    rater's, so ratings stay independent."""
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    rows = db.exec(
        _select(RaterScoreRow).where(
            RaterScoreRow.session_id == session_id,
            RaterScoreRow.user_id == viewer.user.id,
            col(RaterScoreRow.superseded_at).is_(None),
        )
    ).all()
    return [RaterScoreRead.model_validate(r, from_attributes=True) for r in rows]


@router.get("/ratings", response_model=list[RaterScoreRead])
def list_all_ratings(
    rater_id: str | None = None,
    history: bool = False,
    db: DBSession = Depends(db_session),
    _: Viewer = Depends(require_researcher),
) -> list[RaterScoreRead]:
    """Bulk read for the aggregation script (researchers): every rater's current
    scores, or with `history` the replaced ones too."""
    stmt = _select(RaterScoreRow).order_by(col(RaterScoreRow.created_at))
    if rater_id:
        stmt = stmt.where(RaterScoreRow.rater_id == rater_id)
    if not history:
        stmt = stmt.where(col(RaterScoreRow.superseded_at).is_(None))
    return [RaterScoreRead.model_validate(r, from_attributes=True) for r in db.exec(stmt).all()]

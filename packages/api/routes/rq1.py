"""RQ1 study endpoints — rater-score storage + bulk read.

Pairs with the dashboard `RQ1RaterCard`. Ratings live in the
`rq1_rating` table so the study can pool data across raters and
machines. The advice generations they're rating live in
`coach_advice_cache` (filled by the `/sessions/{id}/advice` route).

Each score belongs to the signed-in rater, under a code made from their account
("R-" + the start of its id), never a typed name another rater could reuse; a
changed score is a new row and the old one is kept (ADR-036).

Only researchers and the coaches a researcher chose as raters see the rater card
or can score (ADR-045): `GET/POST /studies/rq1/raters`, `DELETE …/raters/{user}`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
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
    Rq1RaterRow,
    SessionRepo,
    User,
    UserRole,
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
    can_rate: bool  # a researcher, or a coach chosen as a rater (ADR-045)


def may_rate(viewer: Viewer, db: DBSession) -> bool:
    if viewer.researcher:
        return True
    return (
        db.exec(_select(Rq1RaterRow).where(Rq1RaterRow.user_id == viewer.user.id)).first()
        is not None
    )


def _require_rater(viewer: Viewer, db: DBSession) -> None:
    if not may_rate(viewer, db):
        raise HTTPException(
            status_code=403, detail="Only the raters a researcher chose can rate (RQ1)"
        )


@router.get("/me", response_model=RaterMe)
def me(viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)) -> RaterMe:
    return RaterMe(rater_id=rater_code(viewer.user), can_rate=may_rate(viewer, db))


class RaterOut(BaseModel):
    user_id: UUID
    name: str
    email: str
    rater_id: str
    ratings: int  # current scores
    enrolled_at: datetime


class RaterIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)


def _rater_out(db: DBSession, row: Rq1RaterRow) -> RaterOut:
    user = db.get(User, row.user_id)
    n = len(
        db.exec(
            _select(RaterScoreRow.id).where(
                RaterScoreRow.user_id == row.user_id, col(RaterScoreRow.superseded_at).is_(None)
            )
        ).all()
    )
    return RaterOut(
        user_id=row.user_id,
        name=user.name if user else "—",
        email=user.email if user else "—",
        rater_id=rater_code(user) if user else "—",
        ratings=n,
        enrolled_at=row.enrolled_at,
    )


@router.get("/raters", response_model=list[RaterOut])
def list_raters(
    _: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> list[RaterOut]:
    rows = db.exec(_select(Rq1RaterRow).order_by(col(Rq1RaterRow.enrolled_at))).all()
    return [_rater_out(db, r) for r in rows]


@router.post("/raters", response_model=RaterOut, status_code=201)
def add_rater(
    body: RaterIn, viewer: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> RaterOut:
    """Choose a coach account as an RQ1 rater."""
    user = db.exec(
        _select(User).where(func.lower(User.email) == body.email.strip().lower())
    ).first()
    if user is None:
        raise HTTPException(status_code=404, detail="No account with that email")
    if user.role != UserRole.COACH:
        raise HTTPException(status_code=422, detail="RQ1 raters are coach accounts")
    if db.exec(_select(Rq1RaterRow).where(Rq1RaterRow.user_id == user.id)).first():
        raise HTTPException(status_code=409, detail="Already a rater")
    row = Rq1RaterRow(user_id=user.id, enrolled_by=viewer.user.id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _rater_out(db, row)


@router.delete("/raters/{user_id}", status_code=204)
def remove_rater(
    user_id: UUID, _: Viewer = Depends(require_researcher), db: DBSession = Depends(db_session)
) -> None:
    """Stop a coach rating; the scores they gave are kept."""
    row = db.exec(_select(Rq1RaterRow).where(Rq1RaterRow.user_id == user_id)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Not a rater")
    db.delete(row)
    db.commit()


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
    _require_rater(viewer, db)

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
    _require_rater(viewer, db)
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

"""Two-fighter bouts (ADR-011).

A bout links two single-fighter sessions — one per corner (red/blue). This router
creates bouts, assigns each fighter's session to a corner (with the one-red-one-blue,
two-max, one-bout-per-session rules enforced in `BoutRepo`), lists a bout's two
participant sessions, and records the result. The per-fighter streams stay on their
own sessions, so nothing here duplicates punch/IMU/HRV data.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import access
from api.deps import bout_repo
from api.routes.auth import require_current_user
from store import (
    BoutCreate,
    BoutOutcomeEnum,
    BoutRead,
    BoutRepo,
    CornerEnum,
    SessionRead,
)
from store import Session as SessionRow

router = APIRouter(
    prefix="/bouts",
    tags=["bouts"],
    dependencies=[Depends(require_current_user)],
)


class AssignCornerBody(BaseModel):
    session_id: UUID
    corner: CornerEnum


class BoutResultBody(BaseModel):
    winner_corner: BoutOutcomeEnum | None = None
    result_method: str | None = None


@router.post("", response_model=BoutRead, status_code=201)
def create_bout(data: BoutCreate, repo: BoutRepo = Depends(bout_repo)) -> BoutRead:
    return BoutRead.model_validate(repo.create(data), from_attributes=True)


@router.get("", response_model=list[BoutRead])
def list_bouts(
    repo: BoutRepo = Depends(bout_repo), viewer: access.Viewer = Depends(access.require_viewer)
) -> list[BoutRead]:
    """Bouts with a corner this account may see (ADR-017); an empty bout is open to
    those who set fights up."""
    visible = access.visible_fighters(viewer, access.Level.TRAINING)
    sets_up = viewer.coach_id is not None or viewer.manager_gym is not None or viewer.own_fighter
    out = []
    for b in repo.list_all():
        corners = [s.fighter_id for s in repo.participants(b.id)]
        if (corners and any(visible is None or f in visible for f in corners)) or (
            not corners and sets_up
        ):
            out.append(BoutRead.model_validate(b, from_attributes=True))
    return out


@router.get("/{bout_id}", response_model=BoutRead)
def get_bout(bout_id: UUID, repo: BoutRepo = Depends(bout_repo)) -> BoutRead:
    bout = repo.get(bout_id)
    if bout is None:
        raise HTTPException(status_code=404, detail="bout not found")
    return BoutRead.model_validate(bout, from_attributes=True)


@router.get("/{bout_id}/participants", response_model=list[SessionRead])
def list_participants(
    bout_id: UUID,
    repo: BoutRepo = Depends(bout_repo),
    viewer: access.Viewer = Depends(access.require_viewer),
) -> list[SessionRead]:
    """The bout's corner sessions this account may see — the other corner's coach
    doesn't get this fighter's session (ADR-017)."""
    if repo.get(bout_id) is None:
        raise HTTPException(status_code=404, detail="bout not found")
    return [
        SessionRead.model_validate(s, from_attributes=True)
        for s in repo.participants(bout_id)
        if viewer.can(s.fighter_id, access.Level.TRAINING)
    ]


@router.post("/{bout_id}/participants", response_model=SessionRead)
def assign_participant(
    bout_id: UUID,
    body: AssignCornerBody,
    repo: BoutRepo = Depends(bout_repo),
    viewer: access.Viewer = Depends(access.require_viewer),
) -> SessionRead:
    """Attach a fighter's session to this bout in the given corner — one you may
    change (ADR-017)."""
    sess = viewer.db.get(SessionRow, body.session_id)
    if sess is not None:
        viewer.require(sess.fighter_id, access.Level.TRAINING_WRITE)
    try:
        sess = repo.assign_corner(bout_id, body.session_id, body.corner)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if sess is None:
        raise HTTPException(status_code=404, detail="bout not found")
    return SessionRead.model_validate(sess, from_attributes=True)


@router.delete("/{bout_id}/participants/{session_id}", response_model=SessionRead)
def remove_participant(
    bout_id: UUID,
    session_id: UUID,
    repo: BoutRepo = Depends(bout_repo),
) -> SessionRead:
    if repo.get(bout_id) is None:
        raise HTTPException(status_code=404, detail="bout not found")
    if session_id not in {s.id for s in repo.participants(bout_id)}:
        raise HTTPException(status_code=404, detail="that session isn't in this bout")
    sess = repo.remove_participant(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionRead.model_validate(sess, from_attributes=True)


@router.patch("/{bout_id}/result", response_model=BoutRead)
def set_result(
    bout_id: UUID,
    body: BoutResultBody,
    repo: BoutRepo = Depends(bout_repo),
) -> BoutRead:
    bout = repo.set_result(bout_id, body.winner_corner, body.result_method)
    if bout is None:
        raise HTTPException(status_code=404, detail="bout not found")
    return BoutRead.model_validate(bout, from_attributes=True)

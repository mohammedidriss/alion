"""Two-fighter bouts (ADR-011).

A bout links two single-fighter sessions — one per corner (red/blue). This router
creates bouts, assigns each fighter's session to a corner (with the one-red-one-blue,
two-max, one-bout-per-session rules enforced in `BoutRepo`), lists a bout's two
participant sessions, and records the result. The per-fighter streams stay on their
own sessions, so nothing here duplicates punch/IMU/HRV data.

The fight card (ADR-069) — fight type, the belts on the line, event and arena,
weight class or catchweight and each corner's weigh-in, officials, promotion —
is set when the bout is created and edited with PATCH. Deleting a bout hides it
and its corners' sessions; their recordings stay (ADR-056).
"""

from __future__ import annotations

import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from api import access
from api.deps import bout_repo
from api.routes.auth import require_current_user
from store import (
    LB_PER_KG,
    SANCTIONING_BODIES,
    TITLE_KINDS,
    WEIGHT_CLASS_LIMITS_LB,
    WEIGHT_CLASSES,
    BoutCreate,
    BoutOutcomeEnum,
    BoutRead,
    BoutRepo,
    BoutUpdate,
    CornerEnum,
    FightTypeEnum,
    SessionRead,
    SessionRepo,
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


# What each kind of fight usually is — the new-fight page's starting values.
FIGHT_TYPES: list[dict[str, Any]] = [
    {"key": "pro_title", "label": "Title fight", "rounds": 12, "round_s": 180, "rest_s": 60},
    {"key": "pro", "label": "Professional (non-title)", "rounds": 8, "round_s": 180, "rest_s": 60},
    {"key": "amateur", "label": "Amateur", "rounds": 3, "round_s": 180, "rest_s": 60},
    {"key": "exhibition", "label": "Exhibition", "rounds": 6, "round_s": 120, "rest_s": 60},
    {"key": "sparring", "label": "Sparring (friendly)", "rounds": 3, "round_s": 180, "rest_s": 60},
]


def _limit_kg(weight_class: str) -> float | None:
    lb = WEIGHT_CLASS_LIMITS_LB.get(weight_class)
    return round(lb / LB_PER_KG, 1) if lb else None


def _check_card(fields: dict[str, Any]) -> dict[str, Any]:
    """Validate the fight card, filling a standard division's weight limit when none
    was given. Belts belong to title fights only, and a title fight needs a belt."""
    fight_type = fields.get("fight_type")
    titles = fields.get("titles") or []
    for t in titles:
        if t.get("body") not in SANCTIONING_BODIES or t.get("kind") not in TITLE_KINDS:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown belt {t!r} — body one of {', '.join(SANCTIONING_BODIES)}",
            )
    if fight_type is not None:
        if fight_type == FightTypeEnum.PRO_TITLE and not titles:
            raise HTTPException(
                status_code=422, detail="A title fight needs the belt(s) on the line"
            )
        if fight_type != FightTypeEnum.PRO_TITLE and titles:
            raise HTTPException(status_code=422, detail="Only a title fight has belts on the line")
    wc = fields.get("weight_class")
    if wc:
        if wc not in WEIGHT_CLASSES:
            raise HTTPException(status_code=422, detail=f"Unknown weight class {wc!r}")
        if fields.get("weight_limit_kg") is None:
            fields["weight_limit_kg"] = _limit_kg(wc)
    if "judges" in fields and fields["judges"] is not None:
        fields["judges"] = [j.strip() for j in fields["judges"] if j and j.strip()]
    return fields


@router.get("/options")
def fight_options() -> dict[str, Any]:
    """What the new-fight page offers: kinds of fight (with their usual rounds), the
    sanctioning bodies and belt kinds, and the divisions with their limits."""
    return {
        "fight_types": FIGHT_TYPES,
        "sanctioning_bodies": list(SANCTIONING_BODIES),
        "title_kinds": list(TITLE_KINDS),
        "weight_classes": [
            {"key": wc, "limit_lb": WEIGHT_CLASS_LIMITS_LB.get(wc), "limit_kg": _limit_kg(wc)}
            for wc in WEIGHT_CLASSES
        ],
    }


@router.post("", response_model=BoutRead, status_code=201)
def create_bout(data: BoutCreate, repo: BoutRepo = Depends(bout_repo)) -> BoutRead:
    fields = _check_card(data.model_dump())
    return BoutRead.model_validate(repo.create(BoutCreate(**fields)), from_attributes=True)


@router.patch("/{bout_id}", response_model=BoutRead)
def update_bout(bout_id: UUID, data: BoutUpdate, repo: BoutRepo = Depends(bout_repo)) -> BoutRead:
    """Edit the fight card — only the fields sent change. Switching away from a title
    fight clears the belts."""
    bout = repo.get(bout_id)
    if bout is None:
        raise HTTPException(status_code=404, detail="bout not found")
    fields = data.model_dump(exclude_unset=True)
    merged = {
        "fight_type": fields.get("fight_type", bout.fight_type),
        "titles": fields.get("titles", bout.titles),
        **{k: v for k, v in fields.items() if k not in ("fight_type", "titles")},
    }
    if merged["fight_type"] != FightTypeEnum.PRO_TITLE and "titles" not in fields:
        merged["titles"] = []
    _check_card(merged)
    for key in ("fight_type", "titles", "weight_limit_kg"):
        if key in merged:
            fields[key] = merged[key]
    updated = repo.update(bout_id, fields)
    return BoutRead.model_validate(updated, from_attributes=True)


@router.delete("/{bout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bout(
    bout_id: UUID,
    repo: BoutRepo = Depends(bout_repo),
    viewer: access.Viewer = Depends(access.require_viewer),
) -> None:
    """Delete a fight from view (ADR-056): it and both corners' sessions are hidden —
    a capture still running stops as Stop does — and every recording stays."""
    from api.routes.sessions import delete_session_route

    if repo.get(bout_id) is None:
        raise HTTPException(status_code=404, detail="bout not found")
    corners = repo.participants(bout_id)
    for s in corners:
        viewer.require(s.fighter_id, access.Level.TRAINING_WRITE)
    for s in corners:
        if s.removed_at is None:
            delete_session_route(s.id, repo=SessionRepo(viewer.db), viewer=viewer)
    repo.update(
        bout_id,
        {"removed_at": datetime.datetime.now(datetime.UTC), "removed_by": viewer.user.id},
    )


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

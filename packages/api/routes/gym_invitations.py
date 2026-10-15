"""A fighter's gym invitations (ADR-035), and the gyms they're in (ADR-050).

A gym that adds a fighter by System ID invites them; the gym's managers see the
fighter's training data only after the fighter accepts here. A fighter leaves a
gym here too: its managers stop seeing their training, and the coach links that
ran through the gym end.

GET  /v2/gym-invitations                   the signed-in fighter's open invitations
POST /v2/gym-invitations/{id}/accept       join the gym
POST /v2/gym-invitations/{id}/decline      say no (the gym may ask again)
GET  /v2/my-gyms                           the gyms the signed-in fighter is in
POST /v2/my-gyms/{id}/leave                leave one
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.access import Viewer, gym_leaders, require_viewer
from api.deps import db_session
from store import Fighter, Gym, GymRepo
from store.models import GymMembership, MembershipStatus, UtcDatetime

router = APIRouter(prefix="/v2/gym-invitations", tags=["gyms"])
my_gyms = APIRouter(prefix="/v2/my-gyms", tags=["gyms"])

# A fighter in the gym — the statuses they can leave from.
_IN_THE_GYM = (
    MembershipStatus.ACTIVE,
    MembershipStatus.TRIAL,
    MembershipStatus.FROZEN,
    MembershipStatus.SUSPENDED,
)


class GymInvitation(BaseModel):
    id: int
    gym_id: UUID
    gym_name: str
    gym_city: str | None
    managers: list[str]  # who'll see your training data once you accept
    invited_by: str | None
    invited_at: UtcDatetime


def _mine(viewer: Viewer, db: DBSession, membership_id: int) -> GymMembership:
    row = db.get(GymMembership, membership_id)
    if (
        row is None
        or viewer.own_fighter is None
        or row.member_type != "fighter"
        or row.member_id != viewer.own_fighter
        or row.status != MembershipStatus.INVITED
    ):
        raise HTTPException(status_code=404, detail="No such invitation")
    return row


@router.get("", response_model=list[GymInvitation])
def my_invitations(
    viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> list[GymInvitation]:
    if viewer.own_fighter is None:
        return []
    rows = db.exec(
        select(GymMembership).where(
            GymMembership.member_id == viewer.own_fighter,
            GymMembership.member_type == "fighter",
            GymMembership.status == MembershipStatus.INVITED,
        )
    ).all()
    out = []
    for m in rows:
        gym = db.get(Gym, m.gym_id)
        if gym is None:
            continue
        managers = gym_leaders(db, {gym.id})  # who'd see their training (ADR-052)
        note = m.status_note or ""
        out.append(
            GymInvitation(
                id=m.id or 0,
                gym_id=gym.id,
                gym_name=gym.name,
                gym_city=gym.city,
                managers=managers,
                invited_by=note.removeprefix("Invited by ")
                if note.startswith("Invited by ")
                else None,
                invited_at=m.created_at,
            )
        )
    return sorted(out, key=lambda i: i.invited_at, reverse=True)


@router.post("/{membership_id}/accept", response_model=dict)
def accept(
    membership_id: int,
    viewer: Viewer = Depends(require_viewer),
    db: DBSession = Depends(db_session),
) -> dict[str, str]:
    """Join the gym: its managers see your training data (never your health notes)."""
    row = _mine(viewer, db, membership_id)
    row.status = MembershipStatus.ACTIVE
    row.status_note = None
    row.left_on = None
    row.joined_on = date.today()
    db.add(row)
    fighter = db.get(Fighter, row.member_id)
    gym = db.get(Gym, row.gym_id)
    if fighter is not None and gym is not None:
        # Their gym in gym-filtered lists, as an import did before ADR-035.
        fighter.gym_id = gym.id
        fighter.gym = gym.name
        db.add(fighter)
    db.commit()
    return {"status": "active"}


@router.post("/{membership_id}/decline", response_model=dict)
def decline(
    membership_id: int,
    viewer: Viewer = Depends(require_viewer),
    db: DBSession = Depends(db_session),
) -> dict[str, str]:
    row = _mine(viewer, db, membership_id)
    row.status = MembershipStatus.DECLINED
    row.status_note = f"Declined {datetime.now().date().isoformat()}"
    db.add(row)
    db.commit()
    return {"status": "declined"}


class MyGym(BaseModel):
    id: int  # the membership
    gym_id: UUID
    gym_name: str
    gym_city: str | None
    status: str
    joined_on: date | None


@my_gyms.get("", response_model=list[MyGym])
def my_gym_list(
    viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> list[MyGym]:
    if viewer.own_fighter is None:
        return []
    rows = db.exec(
        select(GymMembership).where(
            GymMembership.member_id == viewer.own_fighter,
            GymMembership.member_type == "fighter",
            col(GymMembership.status).in_(_IN_THE_GYM),
        )
    ).all()
    out = []
    for m in rows:
        gym = db.get(Gym, m.gym_id)
        if gym is not None:
            out.append(
                MyGym(
                    id=m.id or 0,
                    gym_id=gym.id,
                    gym_name=gym.name,
                    gym_city=gym.city,
                    status=str(m.status),
                    joined_on=m.joined_on,
                )
            )
    return sorted(out, key=lambda g: g.gym_name.lower())


@my_gyms.post("/{membership_id}/leave", response_model=dict)
def leave(
    membership_id: int,
    viewer: Viewer = Depends(require_viewer),
    db: DBSession = Depends(db_session),
) -> dict[str, str]:
    """Leave the gym: its managers stop seeing your training from now on, and the
    gym's coaches stop coaching you here. Your sessions stay yours."""
    row = db.get(GymMembership, membership_id)
    if (
        row is None
        or viewer.own_fighter is None
        or row.member_type != "fighter"
        or row.member_id != viewer.own_fighter
        or row.status not in _IN_THE_GYM
    ):
        raise HTTPException(status_code=404, detail="You're not in that gym")
    GymRepo(db).update_membership_status(row.gym_id, membership_id, "left", "Left by the fighter")
    return {"status": "left"}

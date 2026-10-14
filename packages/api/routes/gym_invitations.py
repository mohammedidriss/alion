"""A fighter's gym invitations (ADR-035).

A gym that adds a fighter by System ID invites them; the gym's managers see the
fighter's training data only after the fighter accepts here.

GET  /v2/gym-invitations                   the signed-in fighter's open invitations
POST /v2/gym-invitations/{id}/accept       join the gym
POST /v2/gym-invitations/{id}/decline      say no (the gym may ask again)
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import select

from api.access import Viewer, require_viewer
from api.deps import db_session
from store import Fighter, Gym, GymManager
from store.models import GymMembership, MembershipStatus, UtcDatetime

router = APIRouter(prefix="/v2/gym-invitations", tags=["gyms"])


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
        managers = db.exec(select(GymManager.name).where(GymManager.gym_id == gym.id)).all()
        note = m.status_note or ""
        out.append(
            GymInvitation(
                id=m.id or 0,
                gym_id=gym.id,
                gym_name=gym.name,
                gym_city=gym.city,
                managers=sorted(managers),
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

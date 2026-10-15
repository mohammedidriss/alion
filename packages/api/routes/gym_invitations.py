"""A fighter's gym invitations (ADR-035), and the gyms they're in (ADR-050).

A gym that adds a fighter by System ID invites them; the gym's managers see the
fighter's training data only after the fighter accepts here. A fighter leaves a
gym here too: its managers stop seeing their training, and the coach links that
ran through the gym end.

GET  /v2/gym-invitations                   the signed-in fighter's open invitations
POST /v2/gym-invitations/{id}/accept       join the gym
POST /v2/gym-invitations/{id}/decline      say no (the gym may ask again)
GET  /v2/my-gyms                           the gyms the signed-in fighter is in (or asked to join)
POST /v2/my-gyms/{id}/leave                leave one — or withdraw a request
POST /v2/my-gyms/{id}/accept-rules         accept the gym's rules after they changed
GET  /v2/join/{code}                       the gym a join code is for, and its rules
POST /v2/join/{code}                       ask to join it (ADR-055): the gym approves

Joining — by accepting an invitation or asking with a code — means accepting the
gym's rules when it has any; an emergency contact can be given on the way in.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.access import Viewer, gym_leaders, require_viewer
from api.deps import db_session
from store import Fighter, Gym, GymRepo
from store.models import GymMembership, MembershipStatus, UtcDatetime

router = APIRouter(prefix="/v2/gym-invitations", tags=["gyms"])
my_gyms = APIRouter(prefix="/v2/my-gyms", tags=["gyms"])
join = APIRouter(prefix="/v2/join", tags=["gyms"])

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
    rules: str | None = None  # accepted with the invitation (ADR-055)


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
                rules=gym.rules,
            )
        )
    return sorted(out, key=lambda i: i.invited_at, reverse=True)


class JoiningIn(BaseModel):
    """What joining a gym asks (ADR-055): its rules, and who to call."""

    accept_rules: bool = False
    emergency_contact_name: str | None = Field(default=None, max_length=120)
    emergency_contact_phone: str | None = Field(default=None, max_length=40)
    emergency_contact_relation: str | None = Field(default=None, max_length=60)


def _joining(db: DBSession, row: GymMembership, gym: Gym | None, body: JoiningIn) -> None:
    """The gym's rules accepted (refused without, when it has some), and the
    emergency contact given, on the fighter's profile."""
    if gym is not None and gym.rules:
        if not body.accept_rules:
            raise HTTPException(status_code=422, detail="Accept the gym's rules to join it")
        row.rules_version = gym.rules_version
        row.rules_accepted_at = datetime.now(UTC)
    fighter = db.get(Fighter, row.member_id)
    if fighter is not None and body.emergency_contact_name and body.emergency_contact_phone:
        fighter.emergency_contact_name = body.emergency_contact_name.strip()
        fighter.emergency_contact_phone = body.emergency_contact_phone.strip()
        fighter.emergency_contact_relation = (body.emergency_contact_relation or "").strip() or None
        db.add(fighter)


@router.post("/{membership_id}/accept", response_model=dict)
def accept(
    membership_id: int,
    body: JoiningIn | None = None,
    viewer: Viewer = Depends(require_viewer),
    db: DBSession = Depends(db_session),
) -> dict[str, str]:
    """Join the gym: its managers see your training data (never your health notes)."""
    row = _mine(viewer, db, membership_id)
    _joining(db, row, db.get(Gym, row.gym_id), body or JoiningIn())
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
    status: str  # in the gym, or "applied": waiting for the gym to approve
    joined_on: date | None
    rules: str | None = None
    rules_pending: bool = False  # the rules changed since they accepted them


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
            col(GymMembership.status).in_((*_IN_THE_GYM, MembershipStatus.APPLIED)),
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
                    rules=gym.rules,
                    rules_pending=bool(gym.rules) and m.rules_version != gym.rules_version,
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
        or row.status not in (*_IN_THE_GYM, MembershipStatus.APPLIED)
    ):
        raise HTTPException(status_code=404, detail="You're not in that gym")
    note = "Request withdrawn" if row.status == MembershipStatus.APPLIED else "Left by the fighter"
    GymRepo(db).update_membership_status(row.gym_id, membership_id, "left", note)
    return {"status": "left"}


@my_gyms.post("/{membership_id}/accept-rules", response_model=dict)
def accept_rules(
    membership_id: int,
    viewer: Viewer = Depends(require_viewer),
    db: DBSession = Depends(db_session),
) -> dict[str, int]:
    """Accept the gym's current rules (after they changed)."""
    row = db.get(GymMembership, membership_id)
    if row is None or row.member_id != viewer.own_fighter or row.member_type != "fighter":
        raise HTTPException(status_code=404, detail="You're not in that gym")
    gym = db.get(Gym, row.gym_id)
    row.rules_version = gym.rules_version if gym else None
    row.rules_accepted_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    return {"rules_version": row.rules_version or 0}


class JoinPreview(BaseModel):
    gym_id: UUID
    gym_name: str
    gym_city: str | None
    rules: str | None
    leaders: list[str]  # who'll see your training once the gym approves
    status: str | None  # your membership there already, if any


def _by_code(db: DBSession, code: str) -> Gym:
    gym = db.exec(select(Gym).where(Gym.join_code == code.strip().upper())).first()
    if gym is None:
        raise HTTPException(
            status_code=404, detail="No gym with that code — ask the gym for a new one"
        )
    return gym


def _row(db: DBSession, gym_id: UUID, fighter_id: UUID) -> GymMembership | None:
    rows = db.exec(
        select(GymMembership).where(
            GymMembership.gym_id == gym_id,
            GymMembership.member_id == fighter_id,
            GymMembership.member_type == "fighter",
        )
    ).all()
    return max(rows, key=lambda r: r.created_at) if rows else None


@join.get("/{code}", response_model=JoinPreview)
def join_preview(
    code: str, viewer: Viewer = Depends(require_viewer), db: DBSession = Depends(db_session)
) -> JoinPreview:
    gym = _by_code(db, code)
    row = _row(db, gym.id, viewer.own_fighter) if viewer.own_fighter else None
    return JoinPreview(
        gym_id=gym.id,
        gym_name=gym.name,
        gym_city=gym.city,
        rules=gym.rules,
        leaders=gym_leaders(db, {gym.id}),
        status=str(row.status) if row else None,
    )


@join.post("/{code}", response_model=dict)
def ask_to_join(
    code: str,
    body: JoiningIn,
    viewer: Viewer = Depends(require_viewer),
    db: DBSession = Depends(db_session),
) -> dict[str, str]:
    """Ask to join the gym with its code: it approves before its managers see your
    training. An invitation from it is accepted instead."""
    if viewer.own_fighter is None:
        raise HTTPException(status_code=403, detail="Fighters join gyms with a code")
    gym = _by_code(db, code)
    row = _row(db, gym.id, viewer.own_fighter)
    if row is not None and row.status in (*_IN_THE_GYM, MembershipStatus.APPLIED):
        raise HTTPException(status_code=409, detail=f"Already {row.status} at {gym.name}")
    if row is not None and row.status == MembershipStatus.INVITED:
        return accept(row.id or 0, body, viewer, db)
    if row is None:
        row = GymMembership(gym_id=gym.id, member_id=viewer.own_fighter, member_type="fighter")
    row.status = MembershipStatus.APPLIED
    row.status_note = f"Asked to join {date.today().isoformat()}"
    row.left_on = None
    _joining(db, row, gym, body)
    db.add(row)
    db.commit()
    return {"status": "applied"}

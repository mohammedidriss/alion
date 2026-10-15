"""A gym's staff (ADR-052): owners, managers, head coaches and coaches — a role at
that gym, not an account type. One person can hold several roles, and work at
several gyms. A gym invites; the person accepts.

GET  /gyms/{gym_id}/staff                the gym's staff (its staff and admins)
POST /gyms/{gym_id}/staff                invite someone: {"email" | "system_id", "role"}
POST /gyms/{gym_id}/staff/{id}/end       end a role (its owners and managers)
GET  /v2/my-staff                        the signed-in person's roles and invitations
POST /v2/my-staff/{id}/accept            …accept one
POST /v2/my-staff/{id}/decline           …decline one
POST /v2/my-staff/{id}/leave             …leave one

Ending a coaching role ends the coach links made through the gym (ADR-050). A
gym always keeps an owner: the last one can't leave or be removed, except by an
administrator.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import col, or_, select

from api import access
from api.deps import db_session
from api.routes.auth import require_current_user
from store import (
    COACHING_ROLES,
    MANAGING_ROLES,
    Coach,
    Gym,
    GymStaff,
    GymStaffRead,
    GymStaffRole,
    StaffStatus,
    User,
    UserRole,
)
from store.repo import end_gym_links, end_squad_places

router = APIRouter(prefix="/gyms", tags=["gym-staff"], dependencies=[Depends(require_current_user)])
mine = APIRouter(prefix="/v2/my-staff", tags=["gym-staff"])

_OPEN = (StaffStatus.INVITED, StaffStatus.ACTIVE)
_ORDER = {r: i for i, r in enumerate(GymStaffRole)}


class StaffIn(BaseModel):
    email: str | None = None  # an account
    system_id: str | None = None  # a coach's System ID
    role: GymStaffRole


def _out(db: DBSession, row: GymStaff) -> GymStaffRead:
    gym = db.get(Gym, row.gym_id)
    person = db.get(User, row.user_id) if row.user_id else None
    coach = db.get(Coach, row.coach_id) if row.coach_id else None
    inviter = db.get(User, row.invited_by) if row.invited_by else None
    return GymStaffRead(
        id=row.id or 0,
        gym_id=row.gym_id,
        gym_name=gym.name if gym else "?",
        user_id=row.user_id,
        coach_id=row.coach_id,
        name=person.name if person else coach.name if coach else "?",
        email=(person.removed_email or person.email) if person else coach.email if coach else None,
        role=row.role,
        status=row.status,
        invited_by_name=inviter.name if inviter else None,
        note=row.note,
        created_at=row.created_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
    )


def _manages(viewer: access.Viewer, gym_id: UUID) -> None:
    if not (viewer.admin or gym_id in viewer.managed_gyms):
        raise HTTPException(status_code=403, detail="Only this gym's owners and managers")


def _owners(db: DBSession, gym_id: UUID) -> int:
    q = select(GymStaff.id).where(
        GymStaff.gym_id == gym_id,
        GymStaff.role == GymStaffRole.OWNER,
        GymStaff.status == StaffStatus.ACTIVE,
    )
    return len(db.exec(q).all())


def _end(db: DBSession, row: GymStaff, note: str, *, admin: bool = False) -> None:
    """End a role; a coaching role's links through the gym end with it."""
    if (
        row.role == GymStaffRole.OWNER
        and row.status == StaffStatus.ACTIVE
        and _owners(db, row.gym_id) <= 1
        and not admin
    ):
        raise HTTPException(status_code=409, detail="A gym keeps an owner: add another owner first")
    row.status = StaffStatus.LEFT
    row.ended_at = datetime.now(UTC)
    row.note = note
    db.add(row)
    if row.coach_id is not None and row.role in COACHING_ROLES:
        end_gym_links(db, row.gym_id, coach_id=row.coach_id)
        # …and their squads at the gym, unless they still coach there in another role.
        still = db.exec(
            select(GymStaff.id).where(
                GymStaff.gym_id == row.gym_id,
                GymStaff.coach_id == row.coach_id,
                GymStaff.status == StaffStatus.ACTIVE,
                col(GymStaff.role).in_(COACHING_ROLES),
                GymStaff.id != row.id,
            )
        ).first()
        if still is None:
            end_squad_places(db, row.gym_id, coach_id=row.coach_id)
        coach = db.get(Coach, row.coach_id)
        if coach is not None and coach.gym_id == row.gym_id:
            coach.gym_id = None
            coach.gym = None
            db.add(coach)
    db.commit()


def _start(db: DBSession, row: GymStaff) -> None:
    row.status = StaffStatus.ACTIVE
    row.started_at = datetime.now(UTC)
    db.add(row)
    if row.coach_id is not None:
        coach = db.get(Coach, row.coach_id)
        gym = db.get(Gym, row.gym_id)
        if coach is not None and gym is not None and coach.gym_id is None:
            coach.gym_id, coach.gym = gym.id, gym.name  # their gym in gym-filtered lists
            db.add(coach)
    db.commit()


def add_staff(
    db: DBSession,
    gym_id: UUID,
    *,
    role: GymStaffRole,
    user: User | None,
    coach_id: UUID | None,
    invited_by: UUID | None,
    active: bool,
) -> GymStaff:
    """A role at the gym — active at once (the gym made the account or profile, or
    someone added themselves), else an invitation. Refuses a duplicate."""
    who = []
    if user is not None:
        who.append(GymStaff.user_id == user.id)
    if coach_id is not None:
        who.append(GymStaff.coach_id == coach_id)
    dup = db.exec(
        select(GymStaff).where(
            GymStaff.gym_id == gym_id,
            GymStaff.role == role,
            col(GymStaff.status).in_(_OPEN),
            or_(*who),
        )
    ).first()
    if dup is not None:
        raise HTTPException(
            status_code=409, detail=f"Already {dup.status} as {role.replace('_', ' ')}"
        )
    row = GymStaff(
        gym_id=gym_id,
        user_id=user.id if user else None,
        coach_id=coach_id,
        role=role,
        status=StaffStatus.INVITED,
        invited_by=invited_by,
    )
    db.add(row)
    if active:
        _start(db, row)
    else:
        db.commit()
    db.refresh(row)
    return row


@router.get("/{gym_id}/staff", response_model=list[GymStaffRead])
def list_staff(gym_id: UUID, db: DBSession = Depends(db_session)) -> list[GymStaffRead]:
    """Everyone on the staff, invited and past included (the guard lets the gym's
    staff and admins in)."""
    if db.get(Gym, gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    rows = db.exec(select(GymStaff).where(GymStaff.gym_id == gym_id)).all()
    out = [_out(db, r) for r in rows]
    live = {StaffStatus.ACTIVE: 0, StaffStatus.INVITED: 1}
    return sorted(
        out,
        key=lambda s: (live.get(s.status, 2), _ORDER.get(s.role, 9), s.name.lower()),  # type: ignore[call-overload]
    )


@router.post("/{gym_id}/staff", response_model=GymStaffRead, status_code=status.HTTP_201_CREATED)
def invite_staff(
    gym_id: UUID,
    body: StaffIn,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> GymStaffRead:
    """Invite someone by their account's email, or a coach by System ID. Owners are
    added by an owner (or an administrator); coaches need a coach profile."""
    if db.get(Gym, gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    _manages(viewer, gym_id)
    if (
        body.role == GymStaffRole.OWNER
        and not viewer.admin
        and gym_id not in viewer.gyms_as(frozenset({GymStaffRole.OWNER}))
    ):
        raise HTTPException(status_code=403, detail="Only an owner adds another owner")
    user: User | None = None
    coach_id: UUID | None = None
    if body.email:
        user = db.exec(
            select(User).where(User.email == body.email.lower().strip(), col(User.is_active))
        ).first()
        if user is None:
            raise HTTPException(status_code=404, detail="No active account with that email")
        if user.role == UserRole.COACH:
            coach_id = user.profile_id
    elif body.system_id:
        raw = body.system_id.strip().replace("-", "")
        try:
            coach = db.get(Coach, UUID(raw))
        except ValueError:
            coach = None
        if coach is None:
            raise HTTPException(status_code=404, detail="No coach with that System ID")
        coach_id = coach.id
        user = db.exec(
            select(User).where(User.profile_id == coach.id, User.role == UserRole.COACH)
        ).first()
    else:
        raise HTTPException(status_code=422, detail="Give an email or a coach's System ID")
    if body.role == GymStaffRole.COACH and coach_id is None:
        raise HTTPException(status_code=422, detail="A coach needs a coach account")
    if body.role in MANAGING_ROLES and user is None:
        raise HTTPException(status_code=422, detail="An owner or manager needs an account")
    row = add_staff(
        db,
        gym_id,
        role=body.role,
        user=user,
        coach_id=coach_id,
        invited_by=viewer.user.id,
        # Adding yourself, or a coach profile nobody signs in to, needs no answer.
        active=(user is not None and user.id == viewer.user.id) or user is None,
    )
    return _out(db, row)


@router.post("/{gym_id}/staff/{staff_id}/end", response_model=GymStaffRead)
def end_staff(
    gym_id: UUID,
    staff_id: int,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> GymStaffRead:
    _manages(viewer, gym_id)
    row = db.get(GymStaff, staff_id)
    if row is None or row.gym_id != gym_id or row.status not in _OPEN:
        raise HTTPException(status_code=404, detail="No such role at this gym")
    if (
        row.role == GymStaffRole.OWNER
        and not viewer.admin
        and gym_id not in viewer.gyms_as(frozenset({GymStaffRole.OWNER}))
    ):
        raise HTTPException(status_code=403, detail="Only an owner removes an owner")
    _end(db, row, f"Ended by {viewer.user.name}", admin=viewer.admin)
    db.refresh(row)
    return _out(db, row)


def _my_row(viewer: access.Viewer, db: DBSession, staff_id: int) -> GymStaff:
    row = db.get(GymStaff, staff_id)
    mine_ = row is not None and (
        row.user_id == viewer.user.id
        or (viewer.coach_id is not None and row.coach_id == viewer.coach_id)
    )
    if row is None or not mine_:
        raise HTTPException(status_code=404, detail="No such role")
    return row


@mine.get("", response_model=list[GymStaffRead])
def my_staff(
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> list[GymStaffRead]:
    who = [GymStaff.user_id == viewer.user.id]
    if viewer.coach_id is not None:
        who.append(GymStaff.coach_id == viewer.coach_id)
    rows = db.exec(select(GymStaff).where(or_(*who), col(GymStaff.status).in_(_OPEN))).all()
    return sorted((_out(db, r) for r in rows), key=lambda s: (s.status != "invited", s.gym_name))


@mine.post("/{staff_id}/accept", response_model=GymStaffRead)
def accept(
    staff_id: int,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> GymStaffRead:
    row = _my_row(viewer, db, staff_id)
    if row.status != StaffStatus.INVITED:
        raise HTTPException(status_code=409, detail="That invitation isn't open")
    if row.user_id is None:
        row.user_id = viewer.user.id
    _start(db, row)
    db.refresh(row)
    return _out(db, row)


@mine.post("/{staff_id}/decline", response_model=GymStaffRead)
def decline(
    staff_id: int,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> GymStaffRead:
    row = _my_row(viewer, db, staff_id)
    if row.status != StaffStatus.INVITED:
        raise HTTPException(status_code=409, detail="That invitation isn't open")
    row.status = StaffStatus.DECLINED
    row.ended_at = datetime.now(UTC)
    db.add(row)
    db.commit()
    db.refresh(row)
    return _out(db, row)


@mine.post("/{staff_id}/leave", response_model=GymStaffRead)
def leave(
    staff_id: int,
    viewer: access.Viewer = Depends(access.require_viewer),
    db: DBSession = Depends(db_session),
) -> GymStaffRead:
    row = _my_row(viewer, db, staff_id)
    if row.status != StaffStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="You don't hold that role")
    _end(db, row, "Left")
    db.refresh(row)
    return _out(db, row)

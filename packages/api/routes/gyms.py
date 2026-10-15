"""Gym CRUD + membership management.

A fighter a gym adds — by System ID or by profile — is invited, not joined
(ADR-035): the gym's managers see nothing of their training until the fighter
accepts (`/v2/gym-invitations`). Accounts a gym makes itself join at once.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api import access
from api.deps import db_session, gym_repo, resolve_gym_id
from api.routes.auth import get_current_user, require_current_user
from store import (
    CheckInRepo,
    Coach,
    CoachRepo,
    Fighter,
    FighterRepo,
    GymRepo,
    GymStaff,
    GymStaffRole,
    User,
    UserCreate,
    UserRepo,
    UserRole,
)
from store.models import (
    CheckInRead,
    CoachCreate,
    FighterCreate,
    GymCreate,
    GymMembership,
    GymMembershipRead,
    GymRead,
    MembershipStatus,
)

# A fighter's membership the gym can't move on its own: only the fighter accepts.
_FIGHTERS_CALL = {MembershipStatus.INVITED, MembershipStatus.DECLINED, MembershipStatus.LEFT}

router = APIRouter(
    prefix="/gyms",
    tags=["gyms"],
    dependencies=[Depends(require_current_user)],
)


class GymUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = None
    phone: str | None = None
    email: str | None = None
    specialties: str | None = None
    notes: str | None = None


class AddMemberBody(BaseModel):
    member_id: UUID
    member_type: str  # "fighter" or "coach"


class ImportMemberBody(BaseModel):
    system_id: str  # UUID of the fighter or coach profile


class CreateMemberAccountBody(BaseModel):
    name: str
    email: str
    password: str
    role: str  # "fighter" or "coach"


class UpdateMembershipStatusBody(BaseModel):
    status: str  # active, frozen, suspended, trial, left
    note: str | None = None


class CheckInBody(BaseModel):
    member_id: UUID
    member_type: str  # "fighter" or "coach"
    notes: str | None = None


def _read(m: GymMembership, name: str) -> GymMembershipRead:
    return GymMembershipRead(
        id=m.id,
        gym_id=m.gym_id,
        member_id=m.member_id,
        member_type=m.member_type,
        member_name=name,
        status=m.status,
        joined_on=m.joined_on,
        left_on=m.left_on,
        status_note=m.status_note,
        created_at=m.created_at,
    )


def _invite_fighter(session: DBSession, gym_id: UUID, fighter: Fighter, by: User) -> GymMembership:
    """Invite a fighter to the gym (ADR-035) — or again, after they declined or
    left. Refused when they're already in it or already invited."""
    rows = list(
        session.exec(
            select(GymMembership).where(
                GymMembership.gym_id == gym_id,
                GymMembership.member_id == fighter.id,
                GymMembership.member_type == "fighter",
            )
        ).all()
    )
    if any(r.status == MembershipStatus.INVITED for r in rows):
        raise HTTPException(
            status_code=409,
            detail=f"{fighter.name} is already invited — waiting for them to accept",
        )
    gone = [r for r in rows if r.status in _FIGHTERS_CALL]
    in_gym = len(gone) < len(rows) or (fighter.gym_id == gym_id and not gone)
    if in_gym:
        raise HTTPException(
            status_code=409, detail=f"{fighter.name} is already a member of this gym"
        )
    note = f"Invited by {by.name}"[:300]
    if gone:  # ask again on the same row
        row = max(gone, key=lambda r: r.created_at)
        row.status = MembershipStatus.INVITED
        row.status_note = note
        row.left_on = None
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
    return GymRepo(session).add_member(
        gym_id, fighter.id, "fighter", MembershipStatus.INVITED, note
    )


@router.post("", response_model=GymRead, status_code=status.HTTP_201_CREATED)
def create_gym(
    data: GymCreate,
    repo: GymRepo = Depends(gym_repo),
    _admin: access.Viewer = Depends(access.require_admin_viewer),
) -> GymRead:
    return GymRead.model_validate(repo.create(data), from_attributes=True)


@router.get("", response_model=list[GymRead])
def list_gyms(
    repo: GymRepo = Depends(gym_repo),
    current_user: User | None = Depends(get_current_user),
    session: DBSession = Depends(db_session),
) -> list[GymRead]:
    # Gym managers can only see their own gym
    if current_user and current_user.role == "gym_manager":
        scoped_gym = resolve_gym_id(current_user, session)
        if scoped_gym:
            gym = repo.get(scoped_gym)
            return [GymRead.model_validate(gym, from_attributes=True)] if gym else []
    return [GymRead.model_validate(g, from_attributes=True) for g in repo.list_all()]


@router.get("/{gym_id}", response_model=GymRead)
def get_gym(gym_id: UUID, repo: GymRepo = Depends(gym_repo)) -> GymRead:
    row = repo.get(gym_id)
    if row is None:
        raise HTTPException(status_code=404, detail="gym not found")
    return GymRead.model_validate(row, from_attributes=True)


@router.patch("/{gym_id}", response_model=GymRead)
def update_gym(
    gym_id: UUID,
    data: GymUpdate,
    repo: GymRepo = Depends(gym_repo),
) -> GymRead:
    row = repo.update(gym_id, data.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="gym not found")
    return GymRead.model_validate(row, from_attributes=True)


@router.delete("/{gym_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gym(gym_id: UUID, repo: GymRepo = Depends(gym_repo)) -> None:
    if not repo.delete(gym_id):
        raise HTTPException(status_code=404, detail="gym not found")


# ------------------------------------------------------------------
# Membership
# ------------------------------------------------------------------


@router.get("/{gym_id}/members", response_model=list[GymMembershipRead])
def list_members(
    gym_id: UUID,
    include_left: bool = False,
    repo: GymRepo = Depends(gym_repo),
) -> list[GymMembershipRead]:
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    rows = repo.list_members(gym_id, include_left=include_left)
    return [
        GymMembershipRead(
            id=m.id,
            gym_id=m.gym_id,
            member_id=m.member_id,
            member_type=m.member_type,
            member_name=name,
            status=m.status,
            joined_on=m.joined_on,
            left_on=m.left_on,
            status_note=m.status_note,
            created_at=m.created_at,
        )
        for m, name in rows
    ]


def _staff_reply(row: GymStaff, name: str) -> GymMembershipRead:
    """A coach joins the gym's staff (ADR-052), not its members: the reply to an add
    or import describes the staff role in the members list's shape."""
    return GymMembershipRead(
        id=row.id or 0,
        gym_id=row.gym_id,
        member_id=row.coach_id or UUID(int=0),
        member_type="coach",
        member_name=name,
        status=row.status,
        joined_on=row.started_at.date() if row.started_at else None,
        created_at=row.created_at,
    )


def _invite_coach(db: DBSession, gym_id: UUID, coach: Coach, by: User) -> GymMembershipRead:
    """A coach added by profile or System ID is invited to the staff as a coach; a
    profile nobody signs in to joins at once."""
    from api.routes.gym_staff import add_staff

    account = db.exec(
        select(User).where(User.profile_id == coach.id, User.role == UserRole.COACH)
    ).first()
    row = add_staff(
        db,
        gym_id,
        role=GymStaffRole.COACH,
        user=account,
        coach_id=coach.id,
        invited_by=by.id,
        active=account is None,
    )
    return _staff_reply(row, coach.name)


@router.post(
    "/{gym_id}/members",
    response_model=GymMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    gym_id: UUID,
    data: AddMemberBody,
    repo: GymRepo = Depends(gym_repo),
    session: DBSession = Depends(db_session),
    current_user: User = Depends(require_current_user),
) -> GymMembershipRead:
    """Add a coach, or invite a fighter (ADR-035)."""
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    if data.member_type not in ("fighter", "coach"):
        raise HTTPException(status_code=422, detail="member_type must be 'fighter' or 'coach'")
    if data.member_type == "fighter":
        fighter = FighterRepo(session).get(data.member_id)
        if fighter is None:
            raise HTTPException(status_code=404, detail="fighter not found")
        return _read(_invite_fighter(session, gym_id, fighter, current_user), fighter.name)
    coach = CoachRepo(session).get(data.member_id)
    if coach is None:
        raise HTTPException(status_code=404, detail="coach not found")
    return _invite_coach(session, gym_id, coach, current_user)


@router.delete(
    "/{gym_id}/members/{membership_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    gym_id: UUID,
    membership_id: int,
    repo: GymRepo = Depends(gym_repo),
) -> None:
    if not repo.remove_member(gym_id, membership_id):
        raise HTTPException(status_code=404, detail="membership not found")


# ------------------------------------------------------------------
# Import existing user by System ID
# ------------------------------------------------------------------


@router.post(
    "/{gym_id}/members/import",
    response_model=GymMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def import_member(
    gym_id: UUID,
    data: ImportMemberBody,
    repo: GymRepo = Depends(gym_repo),
    session: DBSession = Depends(db_session),
    current_user: User = Depends(require_current_user),
) -> GymMembershipRead:
    """Import an existing coach into a gym by their System ID, or invite a
    fighter — they accept before the gym sees their training (ADR-035)."""
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")

    # Verify the manager owns this gym
    if current_user.role == "gym_manager":
        allowed = resolve_gym_id(current_user, session)
        if allowed != gym_id and str(allowed).replace("-", "") != str(gym_id).replace("-", ""):
            raise HTTPException(status_code=403, detail="You can only manage your own gym")

    system_id = data.system_id.strip().replace("-", "")
    if len(system_id) != 32:
        raise HTTPException(status_code=422, detail="Invalid System ID format")

    system_uuid = UUID(system_id)

    # Try to find as fighter first, then coach
    fighter_repo = FighterRepo(session)
    coach_repo = CoachRepo(session)
    member_type: str | None = None
    member_name = ""

    fighter = fighter_repo.get(system_uuid)
    if fighter:
        member_type = "fighter"
        member_name = fighter.name
    else:
        coach = coach_repo.get(system_uuid)
        if coach:
            member_type = "coach"
            member_name = coach.name

    if member_type is None:
        raise HTTPException(
            status_code=404,
            detail="No fighter or coach found with that System ID",
        )
    if member_type == "fighter" and fighter:
        return _read(_invite_fighter(session, gym_id, fighter, current_user), member_name)

    assert coach is not None
    return _invite_coach(session, gym_id, coach, current_user)


# ------------------------------------------------------------------
# Create a brand-new user account + link to gym
# ------------------------------------------------------------------


@router.post(
    "/{gym_id}/members/create-account",
    response_model=GymMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def create_member_account(
    gym_id: UUID,
    data: CreateMemberAccountBody,
    repo: GymRepo = Depends(gym_repo),
    session: DBSession = Depends(db_session),
    current_user: User = Depends(require_current_user),
) -> GymMembershipRead:
    """Create a new user account (fighter/coach) and add them to the gym."""
    import bcrypt as _bcrypt

    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")

    # Verify the manager owns this gym
    if current_user.role == "gym_manager":
        allowed = resolve_gym_id(current_user, session)
        if allowed != gym_id and str(allowed).replace("-", "") != str(gym_id).replace("-", ""):
            raise HTTPException(status_code=403, detail="You can only manage your own gym")

    if data.role not in ("fighter", "coach"):
        raise HTTPException(status_code=422, detail="role must be 'fighter' or 'coach'")

    email = data.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=422, detail="Invalid email")
    if len(data.password) < 6:
        raise HTTPException(status_code=422, detail="Password must be at least 6 characters")
    if not data.name.strip():
        raise HTTPException(status_code=422, detail="Name is required")

    # Check email uniqueness
    user_repo = UserRepo(session)
    if user_repo.get_by_email(email):
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create user account
    hashed = _bcrypt.hashpw(data.password.encode(), _bcrypt.gensalt()).decode()
    user_create = UserCreate(
        email=email,
        password=data.password,
        name=data.name.strip(),
        role=data.role,
    )
    new_user = user_repo.create(user_create, hashed)

    # Create profile with gym linkage
    gym = repo.get(gym_id)
    gym_name = gym.name if gym else None
    if data.role == "fighter":
        f_repo = FighterRepo(session)
        profile: Fighter | Coach = f_repo.create(
            FighterCreate(name=data.name.strip(), stance="orthodox")
        )
        profile.gym_id = gym_id
        profile.gym = gym_name
        session.add(profile)
        session.commit()
        session.refresh(profile)
        member_type = "fighter"
    else:
        c_repo = CoachRepo(session)
        profile = c_repo.create(CoachCreate(name=data.name.strip()))
        profile.gym_id = gym_id
        profile.gym = gym_name
        session.add(profile)
        session.commit()
        session.refresh(profile)
        member_type = "coach"

    profile_id = profile.id
    user_repo.set_profile_id(new_user.id, profile_id)

    if member_type == "coach":
        from api.routes.gym_staff import add_staff

        staff = add_staff(
            session,
            gym_id,
            role=GymStaffRole.COACH,
            user=new_user,
            coach_id=profile_id,
            invited_by=current_user.id,
            active=True,  # the gym made the account; they accept the terms at first sign-in
        )
        return _staff_reply(staff, data.name.strip())

    # Link to gym
    m = repo.add_member(gym_id, profile_id, member_type)
    return GymMembershipRead(
        id=m.id,
        gym_id=m.gym_id,
        member_id=m.member_id,
        member_type=m.member_type,
        member_name=data.name.strip(),
        status=m.status,
        joined_on=m.joined_on,
        left_on=m.left_on,
        status_note=m.status_note,
        created_at=m.created_at,
    )


# ------------------------------------------------------------------
# Membership status management
# ------------------------------------------------------------------


@router.patch(
    "/{gym_id}/members/{membership_id}/status",
    response_model=GymMembershipRead,
)
def update_membership_status(
    gym_id: UUID,
    membership_id: int,
    data: UpdateMembershipStatusBody,
    repo: GymRepo = Depends(gym_repo),
    session: DBSession = Depends(db_session),
    current_user: User = Depends(require_current_user),
) -> GymMembershipRead:
    """Change a member's status (active, frozen, suspended, trial, left)."""
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")

    valid = {"active", "frozen", "suspended", "trial", "left"}
    if data.status not in valid:
        raise HTTPException(status_code=422, detail=f"status must be one of {valid}")

    # Verify gym manager owns this gym
    if current_user.role == "gym_manager":
        allowed = resolve_gym_id(current_user, session)
        if allowed != gym_id and str(allowed).replace("-", "") != str(gym_id).replace("-", ""):
            raise HTTPException(status_code=403, detail="You can only manage your own gym")

    row = session.get(GymMembership, membership_id)
    if (
        row is not None
        and row.member_type == "fighter"
        and row.status in _FIGHTERS_CALL
        and data.status != "left"
    ):
        raise HTTPException(
            status_code=409,
            detail="Only the fighter can join the gym: invite them by System ID and they accept",
        )
    m = repo.update_membership_status(gym_id, membership_id, data.status, data.note)
    if m is None:
        raise HTTPException(status_code=404, detail="membership not found")

    # Resolve name
    name = ""
    if m.member_type == "fighter":
        f = FighterRepo(session).get(m.member_id)
        if f:
            name = f.name
    else:
        c = CoachRepo(session).get(m.member_id)
        if c:
            name = c.name

    return GymMembershipRead(
        id=m.id,
        gym_id=m.gym_id,
        member_id=m.member_id,
        member_type=m.member_type,
        member_name=name,
        status=m.status,
        joined_on=m.joined_on,
        left_on=m.left_on,
        status_note=m.status_note,
        created_at=m.created_at,
    )


# ------------------------------------------------------------------
# Check-in / Attendance
# ------------------------------------------------------------------


def _checks_in(db: DBSession, gym_id: UUID, member_id: UUID, member_type: str) -> bool:
    """An active or trial member of the gym — or a coach whose profile names it."""
    if member_type == "coach":
        coach = db.get(Coach, member_id)
        if coach is not None and coach.gym_id == gym_id:
            return True
    q = select(GymMembership.id).where(
        GymMembership.gym_id == gym_id,
        GymMembership.member_id == member_id,
        GymMembership.member_type == member_type,
        col(GymMembership.status).in_((MembershipStatus.ACTIVE, MembershipStatus.TRIAL)),
    )
    return db.exec(q).first() is not None


@router.post(
    "/{gym_id}/checkins",
    response_model=CheckInRead,
    status_code=status.HTTP_201_CREATED,
)
def check_in(
    gym_id: UUID,
    data: CheckInBody,
    repo: GymRepo = Depends(gym_repo),
    session: DBSession = Depends(db_session),
    current_user: User = Depends(require_current_user),
) -> CheckInRead:
    """Record a member checking in to the gym."""
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    if data.member_type not in ("fighter", "coach"):
        raise HTTPException(status_code=422, detail="member_type must be 'fighter' or 'coach'")
    if not _checks_in(session, gym_id, data.member_id, data.member_type):
        raise HTTPException(
            status_code=409,
            detail="Only the gym's active or trial members check in (ADR-050)",
        )

    ci_repo = CheckInRepo(session)
    ci = ci_repo.check_in(gym_id, data.member_id, data.member_type, data.notes)

    # Resolve name
    name = ""
    if data.member_type == "fighter":
        f = FighterRepo(session).get(data.member_id)
        if f:
            name = f.name
    else:
        c = CoachRepo(session).get(data.member_id)
        if c:
            name = c.name

    return CheckInRead(
        id=ci.id,
        gym_id=ci.gym_id,
        member_id=ci.member_id,
        member_type=ci.member_type,
        member_name=name,
        checked_in_at=ci.checked_in_at,
        checked_out_at=ci.checked_out_at,
        notes=ci.notes,
    )


@router.post("/{gym_id}/checkins/{checkin_id}/checkout", response_model=CheckInRead)
def check_out(
    gym_id: UUID,
    checkin_id: int,
    session: DBSession = Depends(db_session),
) -> CheckInRead:
    """Record a member checking out of the gym."""
    ci_repo = CheckInRepo(session)
    ci = ci_repo.check_out(checkin_id, gym_id)
    if ci is None:
        raise HTTPException(status_code=404, detail="check-in not found")

    name = ""
    if ci.member_type == "fighter":
        f = FighterRepo(session).get(ci.member_id)
        if f:
            name = f.name
    else:
        c = CoachRepo(session).get(ci.member_id)
        if c:
            name = c.name

    return CheckInRead(
        id=ci.id,
        gym_id=ci.gym_id,
        member_id=ci.member_id,
        member_type=ci.member_type,
        member_name=name,
        checked_in_at=ci.checked_in_at,
        checked_out_at=ci.checked_out_at,
        notes=ci.notes,
    )


@router.get("/{gym_id}/checkins/today", response_model=list[CheckInRead])
def list_todays_checkins(
    gym_id: UUID,
    repo: GymRepo = Depends(gym_repo),
    session: DBSession = Depends(db_session),
) -> list[CheckInRead]:
    """Get today's attendance for the gym."""
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    ci_repo = CheckInRepo(session)
    rows = ci_repo.list_today(gym_id)
    return [
        CheckInRead(
            id=ci.id,
            gym_id=ci.gym_id,
            member_id=ci.member_id,
            member_type=ci.member_type,
            member_name=name,
            checked_in_at=ci.checked_in_at,
            checked_out_at=ci.checked_out_at,
            notes=ci.notes,
        )
        for ci, name in rows
    ]

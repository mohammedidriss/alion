"""Gym CRUD + membership management."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sqlmodel import Session as DBSession

from api.deps import db_session, gym_repo, resolve_gym_id
from api.routes.auth import get_current_user, require_current_user
from store import GymRepo, CheckInRepo, User, UserCreate, UserRepo, FighterRepo, CoachRepo
from store.models import (
    CheckInRead,
    GymCreate,
    GymMembershipRead,
    GymRead,
    FighterCreate,
    CoachCreate,
    Fighter,
    Coach,
    MembershipStatus,
)

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


@router.post("", response_model=GymRead, status_code=status.HTTP_201_CREATED)
def create_gym(data: GymCreate, repo: GymRepo = Depends(gym_repo)) -> GymRead:
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
            id=m.id,  # type: ignore[arg-type]
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


@router.post(
    "/{gym_id}/members",
    response_model=GymMembershipRead,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    gym_id: UUID,
    data: AddMemberBody,
    repo: GymRepo = Depends(gym_repo),
) -> GymMembershipRead:
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    if data.member_type not in ("fighter", "coach"):
        raise HTTPException(status_code=422, detail="member_type must be 'fighter' or 'coach'")
    m = repo.add_member(gym_id, data.member_id, data.member_type)
    name = ""
    return GymMembershipRead(
        id=m.id,  # type: ignore[arg-type]
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
    """Import an existing fighter or coach into a gym by their System ID."""
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

    # Check for duplicate membership
    existing = repo.list_members(gym_id)
    for m, _name in existing:
        if str(m.member_id).replace("-", "") == system_id:
            raise HTTPException(
                status_code=409,
                detail=f"{member_name} is already a member of this gym",
            )

    # Set gym_id on the fighter/coach record so they show in gym-filtered lists
    gym = repo.get(gym_id)
    gym_name = gym.name if gym else None
    if member_type == "fighter" and fighter:
        fighter.gym_id = gym_id
        fighter.gym = gym_name
        session.add(fighter)
        session.commit()
        session.refresh(fighter)
    elif member_type == "coach" and coach:
        coach.gym_id = gym_id
        coach.gym = gym_name
        session.add(coach)
        session.commit()
        session.refresh(coach)

    m = repo.add_member(gym_id, system_uuid, member_type)
    return GymMembershipRead(
        id=m.id,  # type: ignore[arg-type]
        gym_id=m.gym_id,
        member_id=m.member_id,
        member_type=m.member_type,
        member_name=member_name,
        status=m.status,
        joined_on=m.joined_on,
        left_on=m.left_on,
        status_note=m.status_note,
        created_at=m.created_at,
    )


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
        profile = f_repo.create(FighterCreate(name=data.name.strip(), stance="orthodox"))
        profile.gym_id = gym_id  # type: ignore[union-attr]
        profile.gym = gym_name  # type: ignore[union-attr]
        session.add(profile)
        session.commit()
        session.refresh(profile)
        member_type = "fighter"
    else:
        c_repo = CoachRepo(session)
        profile = c_repo.create(CoachCreate(name=data.name.strip()))
        profile.gym_id = gym_id  # type: ignore[union-attr]
        profile.gym = gym_name  # type: ignore[union-attr]
        session.add(profile)
        session.commit()
        session.refresh(profile)
        member_type = "coach"

    profile_id = profile.id  # type: ignore[union-attr]
    user_repo.set_profile_id(new_user.id, profile_id)

    # Link to gym
    m = repo.add_member(gym_id, profile_id, member_type)
    return GymMembershipRead(
        id=m.id,  # type: ignore[arg-type]
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
        id=m.id,  # type: ignore[arg-type]
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
        id=ci.id,  # type: ignore[arg-type]
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
    ci = ci_repo.check_out(checkin_id)
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
        id=ci.id,  # type: ignore[arg-type]
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
            id=ci.id,  # type: ignore[arg-type]
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

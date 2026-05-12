"""Gym CRUD + membership management."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sqlmodel import Session as DBSession

from api.deps import db_session, gym_repo, resolve_gym_id
from api.routes.auth import get_current_user
from store import GymRepo, User
from store.models import GymCreate, GymMembershipRead, GymRead

router = APIRouter(prefix="/gyms", tags=["gyms"])


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
    repo: GymRepo = Depends(gym_repo),
) -> list[GymMembershipRead]:
    if repo.get(gym_id) is None:
        raise HTTPException(status_code=404, detail="gym not found")
    rows = repo.list_members(gym_id)
    return [
        GymMembershipRead(
            id=m.id,  # type: ignore[arg-type]
            gym_id=m.gym_id,
            member_id=m.member_id,
            member_type=m.member_type,
            member_name=name,
            joined_on=m.joined_on,
            left_on=m.left_on,
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
    # Resolve name
    from sqlmodel import Session as DBSession

    name = ""
    return GymMembershipRead(
        id=m.id,  # type: ignore[arg-type]
        gym_id=m.gym_id,
        member_id=m.member_id,
        member_type=m.member_type,
        member_name=name,
        joined_on=m.joined_on,
        left_on=m.left_on,
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

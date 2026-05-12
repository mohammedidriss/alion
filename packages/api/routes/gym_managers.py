"""Gym manager CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from sqlmodel import Session as DBSession

from api.deps import db_session, gym_manager_repo, gym_repo, resolve_gym_id
from api.routes.auth import get_current_user, require_current_user
from store import GymManagerRepo, GymRepo, User
from store.models import GymManagerCreate, GymManagerRead

router = APIRouter(
    prefix="/gym-managers",
    tags=["gym-managers"],
    dependencies=[Depends(require_current_user)],
)


class GymManagerUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    notes: str | None = None


def _enrich(mgr, gym_name: str) -> GymManagerRead:  # type: ignore[no-untyped-def]
    return GymManagerRead(
        id=mgr.id,
        name=mgr.name,
        photo_path=mgr.photo_path,
        email=mgr.email,
        phone=mgr.phone,
        gym_id=mgr.gym_id,
        gym_name=gym_name,
        notes=mgr.notes,
        created_at=mgr.created_at,
    )


@router.post("", response_model=GymManagerRead, status_code=status.HTTP_201_CREATED)
def create_gym_manager(
    data: GymManagerCreate,
    repo: GymManagerRepo = Depends(gym_manager_repo),
    gyms: GymRepo = Depends(gym_repo),
) -> GymManagerRead:
    g = gyms.get(data.gym_id)
    if g is None:
        raise HTTPException(status_code=404, detail="gym not found")
    mgr = repo.create(data)
    return _enrich(mgr, g.name)


@router.get("", response_model=list[GymManagerRead])
def list_gym_managers(
    repo: GymManagerRepo = Depends(gym_manager_repo),
    gyms: GymRepo = Depends(gym_repo),
    current_user: User | None = Depends(get_current_user),
    session: DBSession = Depends(db_session),
) -> list[GymManagerRead]:
    # Gym managers can only see managers in their own gym
    if current_user and current_user.role == "gym_manager":
        scoped_gym = resolve_gym_id(current_user, session)
        if scoped_gym:
            out: list[GymManagerRead] = []
            for mgr in repo.list_all():
                if mgr.gym_id == scoped_gym:
                    g = gyms.get(mgr.gym_id)
                    out.append(_enrich(mgr, g.name if g else "?"))
            return out
    out2: list[GymManagerRead] = []
    for mgr in repo.list_all():
        g = gyms.get(mgr.gym_id)
        out2.append(_enrich(mgr, g.name if g else "?"))
    return out2


@router.get("/{manager_id}", response_model=GymManagerRead)
def get_gym_manager(
    manager_id: UUID,
    repo: GymManagerRepo = Depends(gym_manager_repo),
    gyms: GymRepo = Depends(gym_repo),
) -> GymManagerRead:
    mgr = repo.get(manager_id)
    if mgr is None:
        raise HTTPException(status_code=404, detail="gym manager not found")
    g = gyms.get(mgr.gym_id)
    return _enrich(mgr, g.name if g else "?")


@router.patch("/{manager_id}", response_model=GymManagerRead)
def update_gym_manager(
    manager_id: UUID,
    data: GymManagerUpdate,
    repo: GymManagerRepo = Depends(gym_manager_repo),
    gyms: GymRepo = Depends(gym_repo),
) -> GymManagerRead:
    mgr = repo.update(manager_id, data.model_dump(exclude_unset=True))
    if mgr is None:
        raise HTTPException(status_code=404, detail="gym manager not found")
    g = gyms.get(mgr.gym_id)
    return _enrich(mgr, g.name if g else "?")


@router.delete("/{manager_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gym_manager(
    manager_id: UUID,
    repo: GymManagerRepo = Depends(gym_manager_repo),
) -> None:
    if not repo.delete(manager_id):
        raise HTTPException(status_code=404, detail="gym manager not found")

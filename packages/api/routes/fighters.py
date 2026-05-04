"""Fighter CRUD."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from api.deps import fighter_repo
from store import FighterRepo
from store.models import FighterCreate, FighterRead

router = APIRouter(prefix="/fighters", tags=["fighters"])


@router.post("", response_model=FighterRead, status_code=status.HTTP_201_CREATED)
def create_fighter(data: FighterCreate, repo: FighterRepo = Depends(fighter_repo)) -> FighterRead:
    fighter = repo.create(data)
    return FighterRead.model_validate(fighter, from_attributes=True)


@router.get("", response_model=list[FighterRead])
def list_fighters(repo: FighterRepo = Depends(fighter_repo)) -> list[FighterRead]:
    return [FighterRead.model_validate(f, from_attributes=True) for f in repo.list_all()]


@router.get("/{fighter_id}", response_model=FighterRead)
def get_fighter(fighter_id: UUID, repo: FighterRepo = Depends(fighter_repo)) -> FighterRead:
    fighter = repo.get(fighter_id)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return FighterRead.model_validate(fighter, from_attributes=True)


@router.delete("/{fighter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fighter(fighter_id: UUID, repo: FighterRepo = Depends(fighter_repo)) -> None:
    if not repo.delete(fighter_id):
        raise HTTPException(status_code=404, detail="fighter not found")

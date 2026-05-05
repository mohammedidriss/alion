"""Fighter CRUD + weigh-in tracking."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from api.deps import db_session, fighter_repo
from store import (
    WEIGHT_CLASSES,
    FighterRepo,
    HandEnum,
    SkillLevel,
    Stance,
    WeighInCreate,
    WeighInRead,
    WeighInRepo,
)
from store.models import FighterCreate, FighterRead

router = APIRouter(prefix="/fighters", tags=["fighters"])


class FighterUpdate(BaseModel):
    """Patch payload — every field optional. Send only the keys you want to change."""

    name: str | None = None
    nickname: str | None = None
    dob: date | None = None
    nationality: str | None = None
    sex: str | None = None
    stance: Stance | None = None
    dominant_hand: HandEnum | None = None
    height_cm: float | None = None
    reach_cm: float | None = None
    weight_kg: float | None = None
    shoulder_width_cm: float | None = None
    skill_level: SkillLevel | None = None
    weight_class: str | None = None
    years_training: int | None = None
    gym: str | None = None
    trainer: str | None = None
    record_wins: int | None = None
    record_losses: int | None = None
    record_draws: int | None = None
    record_kos: int | None = None
    boxrec_id: str | None = None
    usa_boxing_id: str | None = None
    notes: str | None = None


@router.get("/options", tags=["fighters"])
def fighter_options() -> dict[str, list[str]]:
    """Static enums + dropdown options the dashboard needs to populate forms."""
    return {
        "stances": [s.value for s in Stance],
        "hands": [h.value for h in HandEnum],
        "skill_levels": [s.value for s in SkillLevel],
        "weight_classes": list(WEIGHT_CLASSES),
        "sexes": ["male", "female", "other"],
    }


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


@router.patch("/{fighter_id}", response_model=FighterRead)
def update_fighter(
    fighter_id: UUID,
    data: FighterUpdate,
    repo: FighterRepo = Depends(fighter_repo),
) -> FighterRead:
    # exclude_unset: only the fields the client actually sent are included.
    patch = data.model_dump(exclude_unset=True)
    fighter = repo.update(fighter_id, patch)
    if fighter is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    return FighterRead.model_validate(fighter, from_attributes=True)


@router.delete("/{fighter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fighter(fighter_id: UUID, repo: FighterRepo = Depends(fighter_repo)) -> None:
    if not repo.delete(fighter_id):
        raise HTTPException(status_code=404, detail="fighter not found")


# ---- weigh-ins ----


@router.get("/{fighter_id}/weigh-ins", response_model=list[WeighInRead])
def list_weigh_ins(
    fighter_id: UUID,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> list[WeighInRead]:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    rows = WeighInRepo(db).list_for_fighter(fighter_id)
    return [WeighInRead.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/{fighter_id}/weigh-ins", response_model=WeighInRead, status_code=status.HTTP_201_CREATED
)
def create_weigh_in(
    fighter_id: UUID,
    data: WeighInCreate,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> WeighInRead:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    row = WeighInRepo(db).create(fighter_id, data)
    return WeighInRead.model_validate(row, from_attributes=True)


@router.delete("/{fighter_id}/weigh-ins/{weigh_in_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_weigh_in(
    fighter_id: UUID,
    weigh_in_id: int,
    repo: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> None:
    if repo.get(fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    if not WeighInRepo(db).delete(weigh_in_id):
        raise HTTPException(status_code=404, detail="weigh-in not found")

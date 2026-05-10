"""Saved round-structure plans (e.g. '3×3 + 1', '12×3 + 1').

Capped at MAX_ROUND_PLANS rows server-side so the dashboard's plan
chooser stays a short, scannable list.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession
from sqlmodel import select

from api.deps import db_session
from store import MAX_ROUND_PLANS, RoundPlanCreate, RoundPlanRead, RoundPlanRow

router = APIRouter(prefix="/round_plans", tags=["round_plans"])


class RoundPlanUpdate(BaseModel):
    """Patch payload — every field optional."""

    name: str | None = Field(default=None, min_length=1, max_length=60)
    round_count: int | None = Field(default=None, ge=1, le=24)
    round_duration_s: int | None = Field(default=None, ge=1, le=900)
    rest_duration_s: int | None = Field(default=None, ge=0, le=600)


@router.get("", response_model=list[RoundPlanRead])
def list_plans(db: DBSession = Depends(db_session)) -> list[RoundPlanRead]:
    rows = list(
        db.exec(
            select(RoundPlanRow).order_by(RoundPlanRow.created_at)  # type: ignore[arg-type]
        ).all()
    )
    return [RoundPlanRead.model_validate(r, from_attributes=True) for r in rows]


@router.post("", response_model=RoundPlanRead, status_code=201)
def create_plan(
    data: RoundPlanCreate,
    db: DBSession = Depends(db_session),
) -> RoundPlanRead:
    existing = list(db.exec(select(RoundPlanRow)).all())
    if len(existing) >= MAX_ROUND_PLANS:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Saved-plan limit reached ({MAX_ROUND_PLANS}). "
                "Delete or update an existing plan instead."
            ),
        )
    row = RoundPlanRow(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return RoundPlanRead.model_validate(row, from_attributes=True)


@router.patch("/{plan_id}", response_model=RoundPlanRead)
def update_plan(
    plan_id: int,
    data: RoundPlanUpdate,
    db: DBSession = Depends(db_session),
) -> RoundPlanRead:
    row = db.get(RoundPlanRow, plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    patch = data.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)
    return RoundPlanRead.model_validate(row, from_attributes=True)


@router.delete("/{plan_id}", status_code=204)
def delete_plan(plan_id: int, db: DBSession = Depends(db_session)) -> None:
    row = db.get(RoundPlanRow, plan_id)
    if row is None:
        raise HTTPException(status_code=404, detail="plan not found")
    db.delete(row)
    db.commit()

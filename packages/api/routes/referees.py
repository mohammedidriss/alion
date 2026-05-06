"""Referee CRUD + photo upload."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from api.deps import referee_repo
from api.services.photos import delete_photos_for, save_photo
from store import RefereeRepo
from store.models import RefereeCreate, RefereeRead

router = APIRouter(prefix="/referees", tags=["referees"])


class RefereeUpdate(BaseModel):
    name: str | None = None
    license_number: str | None = None
    sanctioning_body: str | None = None
    license_expiry: date | None = None
    bio: str | None = None
    notes: str | None = None


@router.post("", response_model=RefereeRead, status_code=status.HTTP_201_CREATED)
def create_referee(
    data: RefereeCreate, repo: RefereeRepo = Depends(referee_repo)
) -> RefereeRead:
    return RefereeRead.model_validate(repo.create(data), from_attributes=True)


@router.get("", response_model=list[RefereeRead])
def list_referees(repo: RefereeRepo = Depends(referee_repo)) -> list[RefereeRead]:
    return [
        RefereeRead.model_validate(r, from_attributes=True) for r in repo.list_all()
    ]


@router.get("/{referee_id}", response_model=RefereeRead)
def get_referee(
    referee_id: UUID, repo: RefereeRepo = Depends(referee_repo)
) -> RefereeRead:
    row = repo.get(referee_id)
    if row is None:
        raise HTTPException(status_code=404, detail="referee not found")
    return RefereeRead.model_validate(row, from_attributes=True)


@router.patch("/{referee_id}", response_model=RefereeRead)
def update_referee(
    referee_id: UUID,
    data: RefereeUpdate,
    repo: RefereeRepo = Depends(referee_repo),
) -> RefereeRead:
    row = repo.update(referee_id, data.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="referee not found")
    return RefereeRead.model_validate(row, from_attributes=True)


@router.delete("/{referee_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_referee(
    referee_id: UUID, repo: RefereeRepo = Depends(referee_repo)
) -> None:
    if not repo.delete(referee_id):
        raise HTTPException(status_code=404, detail="referee not found")
    delete_photos_for("referee", referee_id)


@router.post("/{referee_id}/photo", response_model=RefereeRead)
async def upload_referee_photo(
    referee_id: UUID,
    file: UploadFile = File(...),
    repo: RefereeRepo = Depends(referee_repo),
) -> RefereeRead:
    if repo.get(referee_id) is None:
        raise HTTPException(status_code=404, detail="referee not found")
    path = await save_photo("referee", referee_id, file)
    row = repo.update(referee_id, {"photo_path": path})
    assert row is not None
    return RefereeRead.model_validate(row, from_attributes=True)

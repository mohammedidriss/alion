"""Coach CRUD + photo upload."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from api.deps import coach_repo
from api.services.photos import delete_photos_for, save_photo
from store import CoachingLevel, CoachRepo
from store.models import CoachCreate, CoachRead

router = APIRouter(prefix="/coaches", tags=["coaches"])


class CoachUpdate(BaseModel):
    name: str | None = None
    dob: date | None = None
    nationality: str | None = None
    sex: str | None = None
    email: str | None = None
    phone: str | None = None
    gym: str | None = None
    specialties: str | None = None
    coaching_level: CoachingLevel | None = None
    years_experience: int | None = None
    certifications: str | None = None
    license_number: str | None = None
    license_expiry: date | None = None
    languages: str | None = None
    notable_fighters: str | None = None
    bio: str | None = None
    notes: str | None = None


@router.post("", response_model=CoachRead, status_code=status.HTTP_201_CREATED)
def create_coach(data: CoachCreate, repo: CoachRepo = Depends(coach_repo)) -> CoachRead:
    return CoachRead.model_validate(repo.create(data), from_attributes=True)


@router.get("", response_model=list[CoachRead])
def list_coaches(repo: CoachRepo = Depends(coach_repo)) -> list[CoachRead]:
    return [CoachRead.model_validate(c, from_attributes=True) for c in repo.list_all()]


@router.get("/{coach_id}", response_model=CoachRead)
def get_coach(coach_id: UUID, repo: CoachRepo = Depends(coach_repo)) -> CoachRead:
    row = repo.get(coach_id)
    if row is None:
        raise HTTPException(status_code=404, detail="coach not found")
    return CoachRead.model_validate(row, from_attributes=True)


@router.patch("/{coach_id}", response_model=CoachRead)
def update_coach(
    coach_id: UUID,
    data: CoachUpdate,
    repo: CoachRepo = Depends(coach_repo),
) -> CoachRead:
    row = repo.update(coach_id, data.model_dump(exclude_unset=True))
    if row is None:
        raise HTTPException(status_code=404, detail="coach not found")
    return CoachRead.model_validate(row, from_attributes=True)


@router.delete("/{coach_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_coach(coach_id: UUID, repo: CoachRepo = Depends(coach_repo)) -> None:
    if not repo.delete(coach_id):
        raise HTTPException(status_code=404, detail="coach not found")
    delete_photos_for("coach", coach_id)


@router.post("/{coach_id}/photo", response_model=CoachRead)
async def upload_coach_photo(
    coach_id: UUID,
    file: UploadFile = File(...),
    repo: CoachRepo = Depends(coach_repo),
) -> CoachRead:
    if repo.get(coach_id) is None:
        raise HTTPException(status_code=404, detail="coach not found")
    path = await save_photo("coach", coach_id, file)
    row = repo.update(coach_id, {"photo_path": path})
    assert row is not None
    return CoachRead.model_validate(row, from_attributes=True)

"""Coach CRUD + photo upload + coach notes + assigned fighters."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session as DBSession, select

from api.deps import coach_note_repo, coach_repo, db_session
from api.services.photos import delete_photos_for, save_photo
from store import CoachingLevel, CoachNoteRepo, CoachRepo
from store.models import (
    Coach,
    CoachAssignment,
    CoachCreate,
    CoachNoteCreate,
    CoachNoteRead,
    CoachRead,
    Fighter,
    FighterRead,
)

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
def list_coaches(
    gym_id: UUID | None = None,
    repo: CoachRepo = Depends(coach_repo),
) -> list[CoachRead]:
    rows = repo.list_for_gym(gym_id) if gym_id else repo.list_all()
    return [CoachRead.model_validate(c, from_attributes=True) for c in rows]


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


# ------------------------------------------------------------------
# Assigned fighters
# ------------------------------------------------------------------


@router.get("/{coach_id}/fighters", response_model=list[FighterRead])
def list_assigned_fighters(
    coach_id: UUID,
    repo: CoachRepo = Depends(coach_repo),
    session: DBSession = Depends(db_session),
) -> list[FighterRead]:
    """Return fighters currently assigned to this coach."""
    if repo.get(coach_id) is None:
        raise HTTPException(status_code=404, detail="coach not found")
    stmt = (
        select(Fighter)
        .join(CoachAssignment, CoachAssignment.fighter_id == Fighter.id)  # type: ignore[arg-type]
        .where(
            CoachAssignment.coach_id == coach_id,
            CoachAssignment.ended_on.is_(None),  # type: ignore[union-attr]
        )
    )
    rows = list(session.exec(stmt).all())
    return [FighterRead.model_validate(f, from_attributes=True) for f in rows]


# ------------------------------------------------------------------
# Coach notes
# ------------------------------------------------------------------


@router.post(
    "/{coach_id}/fighters/{fighter_id}/notes",
    response_model=CoachNoteRead,
    status_code=status.HTTP_201_CREATED,
)
def create_coach_note(
    coach_id: UUID,
    fighter_id: UUID,
    data: CoachNoteCreate,
    repo: CoachNoteRepo = Depends(coach_note_repo),
    crepo: CoachRepo = Depends(coach_repo),
) -> CoachNoteRead:
    coach = crepo.get(coach_id)
    if coach is None:
        raise HTTPException(status_code=404, detail="coach not found")
    note = repo.create(coach_id, fighter_id, data.content)
    return CoachNoteRead(
        id=note.id,  # type: ignore[arg-type]
        coach_id=note.coach_id,
        fighter_id=note.fighter_id,
        coach_name=coach.name,
        coach_photo_path=coach.photo_path,
        content=note.content,
        created_at=note.created_at,
    )


@router.get(
    "/{coach_id}/notes",
    response_model=list[CoachNoteRead],
)
def list_coach_notes(
    coach_id: UUID,
    repo: CoachNoteRepo = Depends(coach_note_repo),
    crepo: CoachRepo = Depends(coach_repo),
) -> list[CoachNoteRead]:
    """All notes written by this coach, newest first."""
    if crepo.get(coach_id) is None:
        raise HTTPException(status_code=404, detail="coach not found")
    rows = repo.list_for_coach(coach_id)
    return [
        CoachNoteRead(
            id=note.id,  # type: ignore[arg-type]
            coach_id=note.coach_id,
            fighter_id=note.fighter_id,
            coach_name="",  # not needed in coach-centric view
            content=note.content,
            created_at=note.created_at,
        )
        for note, _fname in rows
    ]


@router.delete(
    "/{coach_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_coach_note(
    coach_id: UUID,
    note_id: int,
    repo: CoachNoteRepo = Depends(coach_note_repo),
) -> None:
    if not repo.delete(note_id, coach_id):
        raise HTTPException(status_code=404, detail="note not found")

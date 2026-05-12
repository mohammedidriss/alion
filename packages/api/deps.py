"""FastAPI dependency providers — the seam where DI happens."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

from fastapi import Depends
from sqlmodel import Session

from store import (
    CoachNoteRepo,
    CoachRepo,
    GymManagerRepo,
    GymRepo,
    ConsensusEventRepo,
    FighterRepo,
    FighterTeamRepo,
    IMUSampleRepo,
    MedicalRepo,
    PunchEventRepo,
    RefereeRepo,
    SessionRepo,
    User,
    get_session,
)


def db_session() -> Iterator[Session]:
    yield from get_session()


def fighter_repo(session: Session = Depends(db_session)) -> FighterRepo:
    return FighterRepo(session)


def session_repo(session: Session = Depends(db_session)) -> SessionRepo:
    return SessionRepo(session)


def punch_event_repo(session: Session = Depends(db_session)) -> PunchEventRepo:
    return PunchEventRepo(session)


def imu_sample_repo(session: Session = Depends(db_session)) -> IMUSampleRepo:
    return IMUSampleRepo(session)


def consensus_event_repo(
    session: Session = Depends(db_session),
) -> ConsensusEventRepo:
    return ConsensusEventRepo(session)


def coach_repo(session: Session = Depends(db_session)) -> CoachRepo:
    return CoachRepo(session)


def referee_repo(session: Session = Depends(db_session)) -> RefereeRepo:
    return RefereeRepo(session)


def medical_repo(session: Session = Depends(db_session)) -> MedicalRepo:
    return MedicalRepo(session)


def fighter_team_repo(session: Session = Depends(db_session)) -> FighterTeamRepo:
    return FighterTeamRepo(session)


def coach_note_repo(session: Session = Depends(db_session)) -> CoachNoteRepo:
    return CoachNoteRepo(session)


def gym_repo(session: Session = Depends(db_session)) -> GymRepo:
    return GymRepo(session)


def gym_manager_repo(session: Session = Depends(db_session)) -> GymManagerRepo:
    return GymManagerRepo(session)


def resolve_gym_id(user: User | None, session: Session) -> UUID | None:
    """Return the gym_id for a gym_manager user, or None for admins/others."""
    if user is None:
        return None
    if user.role == "admin":
        return None  # admins see everything
    if user.role == "gym_manager" and user.profile_id:
        repo = GymManagerRepo(session)
        gm = repo.get(user.profile_id)
        if gm:
            return UUID(str(gm.gym_id))
    return None

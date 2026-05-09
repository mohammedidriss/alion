"""FastAPI dependency providers — the seam where DI happens."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlmodel import Session

from store import (
    CoachRepo,
    ConsensusEventRepo,
    FighterRepo,
    FighterTeamRepo,
    IMUSampleRepo,
    MedicalRepo,
    PunchEventRepo,
    RefereeRepo,
    SessionRepo,
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

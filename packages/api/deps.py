"""FastAPI dependency providers — the seam where DI happens."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Depends
from sqlmodel import Session

from store import FighterRepo, get_session


def db_session() -> Iterator[Session]:
    yield from get_session()


def fighter_repo(session: Session = Depends(db_session)) -> FighterRepo:
    return FighterRepo(session)

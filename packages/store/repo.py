"""Typed repository for Fighter. Thin wrapper over SQLModel; testable in isolation."""

from __future__ import annotations

from uuid import UUID

from sqlmodel import Session, select

from store.models import Fighter, FighterCreate


class FighterRepo:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, data: FighterCreate) -> Fighter:
        fighter = Fighter(**data.model_dump())
        self._session.add(fighter)
        self._session.commit()
        self._session.refresh(fighter)
        return fighter

    def get(self, fighter_id: UUID) -> Fighter | None:
        return self._session.get(Fighter, fighter_id)

    def list_all(self) -> list[Fighter]:
        return list(self._session.exec(select(Fighter)).all())

    def delete(self, fighter_id: UUID) -> bool:
        fighter = self.get(fighter_id)
        if fighter is None:
            return False
        self._session.delete(fighter)
        self._session.commit()
        return True

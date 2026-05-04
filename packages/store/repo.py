"""Typed repositories. Thin wrappers over SQLModel; testable in isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session as DBSession
from sqlmodel import select

from store.models import (
    Fighter,
    FighterCreate,
    PunchEventRow,
    Session,
    SessionCreate,
    SessionStatus,
)


class FighterRepo:
    def __init__(self, session: DBSession) -> None:
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


class SessionRepo:
    def __init__(self, session: DBSession) -> None:
        self._session = session

    def create(self, data: SessionCreate) -> Session:
        row = Session(**data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def get(self, session_id: UUID) -> Session | None:
        return self._session.get(Session, session_id)

    def list_for_fighter(self, fighter_id: UUID) -> list[Session]:
        stmt = select(Session).where(Session.fighter_id == fighter_id)
        return list(self._session.exec(stmt).all())

    def list_all(self) -> list[Session]:
        return list(self._session.exec(select(Session)).all())

    def update_status(
        self, session_id: UUID, status: SessionStatus, end: bool = False
    ) -> Session | None:
        row = self.get(session_id)
        if row is None:
            return None
        row.status = status
        if end:
            row.ended_at = datetime.now(UTC)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def attach_artifacts(
        self,
        session_id: UUID,
        *,
        video_path: str | None = None,
        pose_parquet_path: str | None = None,
        frame_count: int | None = None,
        duration_ms: float | None = None,
    ) -> Session | None:
        row = self.get(session_id)
        if row is None:
            return None
        if video_path is not None:
            row.video_path = video_path
        if pose_parquet_path is not None:
            row.pose_parquet_path = pose_parquet_path
        if frame_count is not None:
            row.frame_count = frame_count
        if duration_ms is not None:
            row.duration_ms = duration_ms
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row


class PunchEventRepo:
    def __init__(self, session: DBSession) -> None:
        self._session = session

    def add_many(self, events: list[PunchEventRow]) -> int:
        for e in events:
            self._session.add(e)
        self._session.commit()
        return len(events)

    def list_for_session(self, session_id: UUID) -> list[PunchEventRow]:
        stmt = (
            select(PunchEventRow)
            .where(PunchEventRow.session_id == session_id)
            .order_by(PunchEventRow.t_ms)  # type: ignore[arg-type]
        )
        return list(self._session.exec(stmt).all())

    def count_for_session(self, session_id: UUID) -> int:
        stmt = select(PunchEventRow).where(PunchEventRow.session_id == session_id)
        return len(list(self._session.exec(stmt).all()))

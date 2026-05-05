"""Typed repositories. Thin wrappers over SQLModel; testable in isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session as DBSession
from sqlmodel import select

from store.models import (
    Fighter,
    FighterCreate,
    HRSampleRow,
    PunchEventRow,
    Session,
    SessionCreate,
    SessionStatus,
    Stance,
    WeighIn,
    WeighInCreate,
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

    def update(self, fighter_id: UUID, patch: dict[str, object]) -> Fighter | None:
        """Apply a partial patch to a fighter row. Unknown keys are ignored.

        Stance / SkillLevel / HandEnum strings are coerced to enum members so
        the API doesn't have to know about SQLModel internals.
        """
        from store.models import HandEnum, SkillLevel

        fighter = self.get(fighter_id)
        if fighter is None:
            return None
        for key, value in patch.items():
            if value is None:
                # Allow nulling out optional fields except `stance`/`name`.
                if key in ("stance", "name"):
                    continue
            if not hasattr(fighter, key):
                continue
            if key == "stance" and isinstance(value, str):
                value = Stance(value)
            elif key == "dominant_hand" and isinstance(value, str):
                value = HandEnum(value)
            elif key == "skill_level" and isinstance(value, str):
                value = SkillLevel(value)
            setattr(fighter, key, value)
        self._session.add(fighter)
        self._session.commit()
        self._session.refresh(fighter)
        return fighter

    def delete(self, fighter_id: UUID) -> bool:
        fighter = self.get(fighter_id)
        if fighter is None:
            return False
        # Cascade through sessions (which themselves cascade to their child rows).
        sessions = SessionRepo(self._session).list_for_fighter(fighter_id)
        for s in sessions:
            SessionRepo(self._session).delete(s.id)
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
        self,
        session_id: UUID,
        status: SessionStatus,
        end: bool = False,
        failure_reason: str | None = None,
    ) -> Session | None:
        row = self.get(session_id)
        if row is None:
            return None
        row.status = status
        if end:
            row.ended_at = datetime.now(UTC)
        if failure_reason is not None:
            row.failure_reason = failure_reason
        elif status != SessionStatus.FAILED:
            row.failure_reason = None
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete(self, session_id: UUID) -> bool:
        row = self.get(session_id)
        if row is None:
            return False
        # Cascade: drop child rows first (no FK CASCADE in SQLite by default).
        from sqlmodel import delete as sqlmodel_delete

        self._session.exec(
            sqlmodel_delete(PunchEventRow).where(PunchEventRow.session_id == session_id)  # type: ignore[arg-type]
        )
        self._session.exec(
            sqlmodel_delete(HRSampleRow).where(HRSampleRow.session_id == session_id)  # type: ignore[arg-type]
        )
        self._session.delete(row)
        self._session.commit()
        return True

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


class WeighInRepo:
    def __init__(self, session: DBSession) -> None:
        self._session = session

    def create(self, fighter_id: UUID, data: WeighInCreate) -> WeighIn:
        row = WeighIn(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        # Mirror the latest weigh-in onto the Fighter row so the profile card
        # can read current weight without a separate query.
        f = self._session.get(Fighter, fighter_id)
        if f is not None:
            f.weight_kg = data.weight_kg
            self._session.add(f)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_for_fighter(self, fighter_id: UUID) -> list[WeighIn]:
        stmt = (
            select(WeighIn).where(WeighIn.fighter_id == fighter_id).order_by(WeighIn.recorded_at)  # type: ignore[arg-type]
        )
        return list(self._session.exec(stmt).all())

    def delete(self, weigh_in_id: int) -> bool:
        row = self._session.get(WeighIn, weigh_in_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

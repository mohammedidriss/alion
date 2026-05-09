"""Typed repositories. Thin wrappers over SQLModel; testable in isolation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session as DBSession
from sqlmodel import select

from store.models import (
    Allergy,
    AllergyCreate,
    Coach,
    CoachAssignment,
    CoachAssignmentCreate,
    CoachCreate,
    ConsensusEventRow,
    Fighter,
    FighterCreate,
    FighterSponsor,
    FighterSponsorCreate,
    FighterTitle,
    FighterTitleCreate,
    HRSampleRow,
    IMUSampleRow,
    MedicalCondition,
    MedicalConditionCreate,
    MedicalRecord,
    Medication,
    MedicationCreate,
    PunchEventRow,
    Referee,
    RefereeCreate,
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
        self._session.exec(
            sqlmodel_delete(IMUSampleRow).where(IMUSampleRow.session_id == session_id)  # type: ignore[arg-type]
        )
        self._session.exec(
            sqlmodel_delete(ConsensusEventRow).where(  # type: ignore[arg-type]
                ConsensusEventRow.session_id == session_id
            )
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

    def attach_baseline(
        self,
        session_id: UUID,
        *,
        rmssd_ms: float,
        sdnn_ms: float,
        mean_hr_bpm: float,
    ) -> Session | None:
        from datetime import UTC, datetime

        row = self.get(session_id)
        if row is None:
            return None
        row.baseline_rmssd_ms = rmssd_ms
        row.baseline_sdnn_ms = sdnn_ms
        row.baseline_mean_hr_bpm = mean_hr_bpm
        row.baseline_recorded_at = datetime.now(UTC)
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


# ----------------------------------------------------------------------
# Coach + Referee
# ----------------------------------------------------------------------


class CoachRepo:
    def __init__(self, session: DBSession) -> None:
        self._session = session

    def create(self, data: CoachCreate) -> Coach:
        row = Coach(**data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def get(self, coach_id: UUID) -> Coach | None:
        return self._session.get(Coach, coach_id)

    def list_all(self) -> list[Coach]:
        return list(self._session.exec(select(Coach).order_by(Coach.name)).all())

    def update(self, coach_id: UUID, patch: dict[str, object]) -> Coach | None:
        row = self.get(coach_id)
        if row is None:
            return None
        for k, v in patch.items():
            if hasattr(row, k):
                setattr(row, k, v)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete(self, coach_id: UUID) -> bool:
        row = self.get(coach_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


class RefereeRepo:
    def __init__(self, session: DBSession) -> None:
        self._session = session

    def create(self, data: RefereeCreate) -> Referee:
        row = Referee(**data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def get(self, referee_id: UUID) -> Referee | None:
        return self._session.get(Referee, referee_id)

    def list_all(self) -> list[Referee]:
        return list(self._session.exec(select(Referee).order_by(Referee.name)).all())

    def update(self, referee_id: UUID, patch: dict[str, object]) -> Referee | None:
        row = self.get(referee_id)
        if row is None:
            return None
        for k, v in patch.items():
            if hasattr(row, k):
                setattr(row, k, v)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete(self, referee_id: UUID) -> bool:
        row = self.get(referee_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


# ----------------------------------------------------------------------
# Medical record + sub-tables
# ----------------------------------------------------------------------


class MedicalRepo:
    """Per-fighter medical record + allergies + medications + conditions."""

    def __init__(self, session: DBSession) -> None:
        self._session = session

    def get_record(self, fighter_id: UUID) -> MedicalRecord | None:
        return self._session.get(MedicalRecord, fighter_id)

    def upsert_record(self, fighter_id: UUID, patch: dict[str, object]) -> MedicalRecord:
        row = self.get_record(fighter_id)
        if row is None:
            row = MedicalRecord(fighter_id=fighter_id)
        for k, v in patch.items():
            if hasattr(row, k):
                setattr(row, k, v)
        row.updated_at = datetime.now(UTC)
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def delete_record(self, fighter_id: UUID) -> bool:
        row = self.get_record(fighter_id)
        if row is None:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    # --- Allergies ---

    def add_allergy(self, fighter_id: UUID, data: AllergyCreate) -> Allergy:
        row = Allergy(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_allergies(self, fighter_id: UUID) -> list[Allergy]:
        stmt = (
            select(Allergy)
            .where(Allergy.fighter_id == fighter_id)
            .order_by(Allergy.severity, Allergy.substance)
        )
        return list(self._session.exec(stmt).all())

    def delete_allergy(self, fighter_id: UUID, allergy_id: int) -> bool:
        row = self._session.get(Allergy, allergy_id)
        if row is None or row.fighter_id != fighter_id:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    # --- Medications ---

    def add_medication(self, fighter_id: UUID, data: MedicationCreate) -> Medication:
        row = Medication(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_medications(self, fighter_id: UUID) -> list[Medication]:
        stmt = (
            select(Medication)
            .where(Medication.fighter_id == fighter_id)
            .order_by(Medication.is_active.desc(), Medication.name)  # type: ignore[attr-defined]
        )
        return list(self._session.exec(stmt).all())

    def delete_medication(self, fighter_id: UUID, medication_id: int) -> bool:
        row = self._session.get(Medication, medication_id)
        if row is None or row.fighter_id != fighter_id:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    # --- Conditions ---

    def add_condition(self, fighter_id: UUID, data: MedicalConditionCreate) -> MedicalCondition:
        row = MedicalCondition(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_conditions(self, fighter_id: UUID) -> list[MedicalCondition]:
        stmt = (
            select(MedicalCondition)
            .where(MedicalCondition.fighter_id == fighter_id)
            .order_by(MedicalCondition.status, MedicalCondition.name)
        )
        return list(self._session.exec(stmt).all())

    def delete_condition(self, fighter_id: UUID, condition_id: int) -> bool:
        row = self._session.get(MedicalCondition, condition_id)
        if row is None or row.fighter_id != fighter_id:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


# ----------------------------------------------------------------------
# Fighter team — titles, sponsors, coach assignments
# ----------------------------------------------------------------------


class FighterTeamRepo:
    """Sub-collections that hang off a fighter for the Team tab.

    Kept separate from FighterRepo so the surface stays small.
    """

    def __init__(self, session: DBSession) -> None:
        self._session = session

    # --- Titles ---

    def add_title(self, fighter_id: UUID, data: FighterTitleCreate) -> FighterTitle:
        row = FighterTitle(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_titles(self, fighter_id: UUID) -> list[FighterTitle]:
        stmt = select(FighterTitle).where(FighterTitle.fighter_id == fighter_id)
        rows = list(self._session.exec(stmt).all())
        rows.sort(key=lambda t: -(t.won_on.toordinal() if t.won_on else 0))
        return rows

    def delete_title(self, fighter_id: UUID, title_id: int) -> bool:
        row = self._session.get(FighterTitle, title_id)
        if row is None or row.fighter_id != fighter_id:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    # --- Sponsors ---

    def add_sponsor(self, fighter_id: UUID, data: FighterSponsorCreate) -> FighterSponsor:
        row = FighterSponsor(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_sponsors(self, fighter_id: UUID) -> list[FighterSponsor]:
        rows = list(
            self._session.exec(
                select(FighterSponsor).where(FighterSponsor.fighter_id == fighter_id)
            ).all()
        )
        # Sort in Python: current (no end date) first, then most-recent start.
        rows.sort(
            key=lambda s: (
                s.ended_on is not None,
                -(s.started_on.toordinal() if s.started_on else 0),
            )
        )
        return rows

    def delete_sponsor(self, fighter_id: UUID, sponsor_id: int) -> bool:
        row = self._session.get(FighterSponsor, sponsor_id)
        if row is None or row.fighter_id != fighter_id:
            return False
        self._session.delete(row)
        self._session.commit()
        return True

    # --- Coach assignments (denormalises coach name+photo for the UI) ---

    def add_coach_assignment(
        self, fighter_id: UUID, data: CoachAssignmentCreate
    ) -> CoachAssignment:
        row = CoachAssignment(fighter_id=fighter_id, **data.model_dump())
        self._session.add(row)
        self._session.commit()
        self._session.refresh(row)
        return row

    def list_coach_assignments(
        self, fighter_id: UUID
    ) -> list[tuple[CoachAssignment, str, str | None]]:
        """Returns (assignment, coach_name, coach_photo_path) tuples for the
        UI; the read DTO denormalises the coach so we don't make N+1 calls."""
        stmt = (
            select(CoachAssignment, Coach.name, Coach.photo_path)
            .join(Coach, Coach.id == CoachAssignment.coach_id)  # type: ignore[arg-type]
            .where(CoachAssignment.fighter_id == fighter_id)
        )
        rows = list(self._session.exec(stmt).all())
        rows.sort(
            key=lambda r: (
                r[0].ended_on is not None,
                -(r[0].started_on.toordinal() if r[0].started_on else 0),
            )
        )
        return rows

    def delete_coach_assignment(self, fighter_id: UUID, assignment_id: int) -> bool:
        row = self._session.get(CoachAssignment, assignment_id)
        if row is None or row.fighter_id != fighter_id:
            return False
        self._session.delete(row)
        self._session.commit()
        return True


class IMUSampleRepo:
    """Per-session IMU samples — accelerometer + gyroscope rows.

    Behaves like PunchEventRepo: bulk insert + ordered list. Used by the
    /sessions/{id}/imu/upload endpoint and by the synthetic generator.
    """

    def __init__(self, session: DBSession) -> None:
        self._session = session

    def add_many(self, samples: list[IMUSampleRow]) -> int:
        for s in samples:
            self._session.add(s)
        self._session.commit()
        return len(samples)

    def replace_for_session(self, session_id: UUID, samples: list[IMUSampleRow]) -> int:
        from sqlmodel import delete as sqlmodel_delete

        self._session.exec(
            sqlmodel_delete(IMUSampleRow).where(IMUSampleRow.session_id == session_id)  # type: ignore[arg-type]
        )
        return self.add_many(samples)

    def list_for_session(self, session_id: UUID) -> list[IMUSampleRow]:
        stmt = (
            select(IMUSampleRow)
            .where(IMUSampleRow.session_id == session_id)
            .order_by(IMUSampleRow.t_ms)  # type: ignore[arg-type]
        )
        return list(self._session.exec(stmt).all())

    def count_for_session(self, session_id: UUID) -> int:
        stmt = select(IMUSampleRow).where(IMUSampleRow.session_id == session_id)
        return len(list(self._session.exec(stmt).all()))


class ConsensusEventRepo:
    """Per-session consensus events — one row per reconciled punch."""

    def __init__(self, session: DBSession) -> None:
        self._session = session

    def replace_for_session(self, session_id: UUID, rows: list[ConsensusEventRow]) -> int:
        from sqlmodel import delete as sqlmodel_delete

        self._session.exec(
            sqlmodel_delete(ConsensusEventRow).where(  # type: ignore[arg-type]
                ConsensusEventRow.session_id == session_id
            )
        )
        for r in rows:
            self._session.add(r)
        self._session.commit()
        return len(rows)

    def list_for_session(self, session_id: UUID) -> list[ConsensusEventRow]:
        stmt = (
            select(ConsensusEventRow)
            .where(ConsensusEventRow.session_id == session_id)
            .order_by(ConsensusEventRow.t_ms)  # type: ignore[arg-type]
        )
        return list(self._session.exec(stmt).all())

    def count_for_session(self, session_id: UUID) -> int:
        return len(self.list_for_session(session_id))

"""SQLModel tables. Phase 0 has only Fighter; Sessions/Rounds land in later phases."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Stance(StrEnum):
    ORTHODOX = "orthodox"
    SOUTHPAW = "southpaw"
    SWITCH = "switch"


class Fighter(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str = Field(index=True, min_length=1, max_length=120)
    dob: date | None = None
    stance: Stance = Stance.ORTHODOX
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FighterCreate(SQLModel):
    name: str = Field(min_length=1, max_length=120)
    dob: date | None = None
    stance: Stance = Stance.ORTHODOX


class FighterRead(SQLModel):
    id: UUID
    name: str
    dob: date | None
    stance: Stance
    created_at: datetime

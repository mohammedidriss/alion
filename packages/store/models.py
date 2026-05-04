"""SQLModel tables.

Pose keypoints are NOT in SQLite — they go to parquet on disk; the Session row
just holds a pointer (`pose_parquet_path`). HR samples and punch events are
tabular and live here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


class Stance(StrEnum):
    ORTHODOX = "orthodox"
    SOUTHPAW = "southpaw"
    SWITCH = "switch"


class SessionSourceEnum(StrEnum):
    LIVE_WEBCAM = "live_webcam"
    UPLOADED_VIDEO = "uploaded_video"
    LIVE_IPHONE = "live_iphone"


class SessionStatus(StrEnum):
    PENDING = "pending"
    CAPTURING = "capturing"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class HandEnum(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class DetectionSourceEnum(StrEnum):
    HEURISTIC = "heuristic"
    LSTM_V1 = "lstm_v1"


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


class Session(SQLModel, table=True):
    id: UUID = Field(default_factory=uuid4, primary_key=True)
    fighter_id: UUID = Field(foreign_key="fighter.id", index=True)
    source: SessionSourceEnum
    status: SessionStatus = SessionStatus.PENDING
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    ended_at: datetime | None = None
    video_path: str | None = None
    pose_parquet_path: str | None = None
    frame_count: int = 0
    duration_ms: float = 0.0
    notes: str | None = None


class SessionCreate(SQLModel):
    fighter_id: UUID
    source: SessionSourceEnum
    notes: str | None = None


class SessionRead(SQLModel):
    id: UUID
    fighter_id: UUID
    source: SessionSourceEnum
    status: SessionStatus
    started_at: datetime
    ended_at: datetime | None
    video_path: str | None
    pose_parquet_path: str | None
    frame_count: int
    duration_ms: float
    notes: str | None


class PunchEventRow(SQLModel, table=True):
    __tablename__ = "punch_event"
    id: int | None = Field(default=None, primary_key=True)
    session_id: UUID = Field(foreign_key="session.id", index=True)
    t_ms: float
    hand: HandEnum
    velocity_ms: float
    detected_by: DetectionSourceEnum
    confidence: float


class PunchEventRead(SQLModel):
    session_id: UUID
    t_ms: float
    hand: HandEnum
    velocity_ms: float
    detected_by: DetectionSourceEnum
    confidence: float

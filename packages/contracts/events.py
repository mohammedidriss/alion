"""Per-stream raw event types — produced by capture, consumed by analyze + store.

Distinct from the fused `SessionSummary` (schema.py): these are the upstream
inputs that feed the fusion engine in Phase 4.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# MediaPipe Pose returns 33 landmarks per frame.
NUM_POSE_LANDMARKS = 33

Hand = Literal["left", "right"]
SessionSource = Literal["live_webcam", "uploaded_video", "live_iphone"]
DetectionSource = Literal["heuristic", "lstm_v1"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Landmark(_Frozen):
    """Normalized image coordinates [0,1] + relative depth + visibility [0,1]."""

    x: float
    y: float
    z: float
    visibility: float = Field(ge=0.0, le=1.0)


class PoseFrame(_Frozen):
    session_id: UUID
    frame_index: int = Field(ge=0)
    t_ms: float = Field(ge=0.0, description="ms since session start")
    landmarks: tuple[Landmark, ...] = Field(
        min_length=NUM_POSE_LANDMARKS, max_length=NUM_POSE_LANDMARKS
    )


class PunchEvent(_Frozen):
    """A detected punch — Phase 1 uses heuristic; Phase 3 swaps in LSTM."""

    session_id: UUID
    t_ms: float = Field(ge=0.0)
    hand: Hand
    velocity_ms: float = Field(ge=0.0, description="peak wrist velocity in m/s (estimated)")
    detected_by: DetectionSource
    confidence: float = Field(ge=0.0, le=1.0)


class SessionMeta(_Frozen):
    """Lightweight session descriptor, mirrors the Session DB row."""

    id: UUID
    fighter_id: UUID
    started_at: datetime
    source: SessionSource
    video_path: str | None = None
    pose_parquet_path: str | None = None
    frame_count: int = 0
    duration_ms: float = 0.0

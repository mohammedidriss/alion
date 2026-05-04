"""session_summary.json — the contract between the Fusion Engine and everything downstream.

Mirrors the JSON in §2 of the build brief. Any change here ripples to every module
that reads or writes a SessionSummary; bump SCHEMA_VERSION on breaking changes.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"

Confidence = float  # 0.0–1.0; validated per-field via Field(ge=0.0, le=1.0)

PhysiologicalState = Literal[
    "rest", "low_intensity", "moderate_intensity", "high_intensity", "maximal"
]
FatigueSignal = Literal["none", "low", "moderate", "high"]
PunchType = Literal["jab", "cross", "hook", "uppercut"]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class PunchTypeCounts(_Frozen):
    jab: int = Field(ge=0, default=0)
    cross: int = Field(ge=0, default=0)
    hook: int = Field(ge=0, default=0)
    uppercut: int = Field(ge=0, default=0)

    @property
    def total(self) -> int:
        return self.jab + self.cross + self.hook + self.uppercut


class CVStream(_Frozen):
    punches_detected: int = Field(ge=0)
    punch_types: PunchTypeCounts
    movement_zones: dict[str, float] = Field(default_factory=dict)
    stance_changes: int = Field(ge=0)
    occlusion_pct: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class IMUStream(_Frozen):
    punches_detected: int = Field(ge=0)
    max_velocity_ms: float = Field(ge=0.0)
    mean_velocity_ms: float = Field(ge=0.0)
    punch_types: PunchTypeCounts
    confidence: float = Field(ge=0.0, le=1.0)


class HRVStream(_Frozen):
    mean_hr_bpm: float = Field(ge=0.0)
    max_hr_bpm: float = Field(ge=0.0)
    rmssd_ms: float = Field(ge=0.0)
    sdnn_ms: float = Field(ge=0.0)
    load_index: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)


class FusionBlock(_Frozen):
    punches_reconciled: int = Field(ge=0)
    cv_imu_agreement_pct: float = Field(ge=0.0, le=1.0)
    physiological_state: PhysiologicalState
    fatigue_signal: FatigueSignal


class SessionSummary(_Frozen):
    """Per-round fused summary. The single source of truth for the LLM coaching layer."""

    schema_version: str = SCHEMA_VERSION
    session_id: UUID
    fighter_id: UUID
    round_number: int = Field(ge=1)
    duration_sec: int = Field(ge=0)
    cv: CVStream
    imu: IMUStream
    hrv: HRVStream
    fusion: FusionBlock

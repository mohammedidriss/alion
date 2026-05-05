"""Contracts — pydantic types shared across all modules.

This package is the single source of truth for inter-module data shapes.
It depends on nothing in this repo; everything depends on it.
"""

from contracts.events import (
    NUM_POSE_LANDMARKS,
    DetectionSource,
    Hand,
    HRMetricsWindow,
    HRSample,
    Landmark,
    PoseFrame,
    PunchEvent,
    SessionMeta,
    SessionSource,
)
from contracts.schema import (
    SCHEMA_VERSION,
    Confidence,
    CVStream,
    FusionBlock,
    HRVStream,
    IMUStream,
    PunchTypeCounts,
    SessionSummary,
)

__all__ = [
    # Raw streams (Phase 1+)
    "NUM_POSE_LANDMARKS",
    # Fused output (Phase 4)
    "SCHEMA_VERSION",
    "CVStream",
    "Confidence",
    "DetectionSource",
    "FusionBlock",
    "HRMetricsWindow",
    "HRSample",
    "HRVStream",
    "Hand",
    "IMUStream",
    "Landmark",
    "PoseFrame",
    "PunchEvent",
    "PunchTypeCounts",
    "SessionMeta",
    "SessionSource",
    "SessionSummary",
]

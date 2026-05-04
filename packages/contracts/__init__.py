"""Contracts — pydantic types shared across all modules.

This package is the single source of truth for inter-module data shapes.
It depends on nothing in this repo; everything depends on it.

Public API:
"""

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
    "SCHEMA_VERSION",
    "CVStream",
    "Confidence",
    "FusionBlock",
    "HRVStream",
    "IMUStream",
    "PunchTypeCounts",
    "SessionSummary",
]

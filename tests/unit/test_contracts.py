"""Schema regression tests. The brief's §2 JSON must round-trip cleanly."""

from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import SCHEMA_VERSION, SessionSummary


def _sample() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": str(uuid4()),
        "fighter_id": str(uuid4()),
        "round_number": 3,
        "duration_sec": 180,
        "cv": {
            "punches_detected": 47,
            "punch_types": {"jab": 22, "cross": 14, "hook": 8, "uppercut": 3},
            "movement_zones": {},
            "stance_changes": 4,
            "occlusion_pct": 0.12,
            "confidence": 0.87,
        },
        "imu": {
            "punches_detected": 51,
            "max_velocity_ms": 8.4,
            "mean_velocity_ms": 5.2,
            "punch_types": {"jab": 24, "cross": 15, "hook": 9, "uppercut": 3},
            "confidence": 0.94,
        },
        "hrv": {
            "mean_hr_bpm": 168,
            "max_hr_bpm": 184,
            "rmssd_ms": 18.3,
            "sdnn_ms": 24.1,
            "load_index": 0.78,
            "confidence": 0.96,
        },
        "fusion": {
            "punches_reconciled": 49,
            "cv_imu_agreement_pct": 0.92,
            "physiological_state": "high_intensity",
            "fatigue_signal": "moderate",
        },
    }


def test_session_summary_round_trip() -> None:
    summary = SessionSummary.model_validate(_sample())
    assert summary.cv.punch_types.total == 47
    assert summary.fusion.physiological_state == "high_intensity"
    assert summary.schema_version == SCHEMA_VERSION


def test_confidence_must_be_in_range() -> None:
    bad = _sample()
    bad["cv"]["confidence"] = 1.5
    with pytest.raises(ValidationError):
        SessionSummary.model_validate(bad)


def test_unknown_field_rejected() -> None:
    bad = _sample()
    bad["mystery_field"] = 42
    with pytest.raises(ValidationError):
        SessionSummary.model_validate(bad)

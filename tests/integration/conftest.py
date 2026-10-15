"""Integration-test fixtures shared by the API tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _no_background_cross_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pose upload starts a cross-check, and a saved take a pose recovery, in
    background threads that would outlive the test's database; tests run them
    themselves (cross_check.run_now, pose_backfill.recover_take)."""
    from api.services import cross_check, pose_backfill

    monkeypatch.setattr(cross_check, "BACKGROUND", False)
    monkeypatch.setattr(pose_backfill, "BACKGROUND", False)


@pytest.fixture(autouse=True)
def recorded(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Model training also reads the recorded sessions on disk (ADR-047); a test
    sees none unless it lays some down here."""
    from api.services import session_corpus

    root = tmp_path_factory.mktemp("recorded")
    monkeypatch.setattr(session_corpus, "LABELS_DIR", root / "labels")
    monkeypatch.setattr(session_corpus, "POSE_DIR", root / "processed")
    monkeypatch.setattr(session_corpus, "imu_streams", lambda sid: {})  # not the real database
    # …and counts the cameras' punches with the detector unless a test trains a counter.
    from api.services import punch_counter

    monkeypatch.setattr(punch_counter, "MODELS_DIR", root / "counters")
    return root

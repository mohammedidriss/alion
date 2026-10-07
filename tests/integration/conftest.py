"""Integration-test fixtures shared by the API tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_background_cross_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pose upload starts a cross-check, and a saved take a pose recovery, in
    background threads that would outlive the test's database; tests run them
    themselves (cross_check.run_now, pose_backfill.recover_take)."""
    from api.services import cross_check, pose_backfill

    monkeypatch.setattr(cross_check, "BACKGROUND", False)
    monkeypatch.setattr(pose_backfill, "BACKGROUND", False)

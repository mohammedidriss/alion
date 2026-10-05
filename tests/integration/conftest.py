"""Integration-test fixtures shared by the API tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_background_cross_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pose upload starts a cross-check in a background thread, which would
    outlive the test's database; tests run it themselves (cross_check.run_now)."""
    from api.services import cross_check

    monkeypatch.setattr(cross_check, "BACKGROUND", False)

"""SessionClock — anchor + offset math for cross-modality alignment."""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest

from common import SessionClock


def test_start_anchors_to_now_when_no_arg() -> None:
    before = datetime.now(UTC)
    c = SessionClock.start()
    after = datetime.now(UTC)
    assert before <= c.wall_t0 <= after
    assert c.monotonic_ns_t0 > 0


def test_start_with_explicit_wall_t0() -> None:
    t0 = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    c = SessionClock.start(wall_t0=t0)
    assert c.wall_t0 == t0


def test_now_offset_ms_starts_near_zero_and_advances() -> None:
    c = SessionClock.start()
    immediate = c.now_offset_ms()
    assert 0 <= immediate < 50  # construction overhead bounded
    time.sleep(0.05)
    later = c.now_offset_ms()
    assert later > immediate
    # Should be ~50 ms further along, but allow generous slack on CI.
    assert later - immediate >= 40


def test_offset_from_monotonic_ns_matches_now_offset_ms() -> None:
    c = SessionClock.start()
    ns = time.monotonic_ns()
    via_ns = c.offset_from_monotonic_ns(ns)
    via_now = c.now_offset_ms()
    # Both readings sampled near each other; should agree within 5 ms.
    assert abs(via_ns - via_now) < 5


def test_offset_from_wall_positive_after_t0() -> None:
    t0 = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    c = SessionClock.start(wall_t0=t0)
    later = t0 + timedelta(milliseconds=1234)
    assert c.offset_from_wall(later) == pytest.approx(1234.0)


def test_offset_from_wall_negative_before_t0() -> None:
    t0 = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    c = SessionClock.start(wall_t0=t0)
    earlier = t0 - timedelta(milliseconds=500)
    assert c.offset_from_wall(earlier) == pytest.approx(-500.0)


def test_wall_for_offset_inverts_offset_from_wall() -> None:
    t0 = datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)
    c = SessionClock.start(wall_t0=t0)
    target = t0 + timedelta(milliseconds=2700)
    assert c.wall_for_offset(c.offset_from_wall(target)) == target


def test_clock_is_frozen_dataclass() -> None:
    """Frozen dataclasses raise FrozenInstanceError on attribute set."""
    from dataclasses import FrozenInstanceError

    c = SessionClock.start()
    with pytest.raises(FrozenInstanceError):
        c.wall_t0 = datetime.now(UTC)  # type: ignore[misc]

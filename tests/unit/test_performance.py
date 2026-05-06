"""compute_score: transparent v1 performance formula."""

from __future__ import annotations

import pytest

from analyze import compute_score


def test_empty_events_returns_zero() -> None:
    s = compute_score([], duration_ms=60_000)
    assert s.peak_velocity_p90 == 0.0
    assert s.ppm == 0.0
    assert s.score == 0.0


def test_zero_duration_returns_zero_ppm() -> None:
    s = compute_score([3.0, 4.0], duration_ms=0)
    assert s.ppm == 0.0
    assert s.score == 0.0
    # p90 still computed even when duration is zero
    assert s.peak_velocity_p90 > 0


def test_single_punch() -> None:
    s = compute_score([5.0], duration_ms=60_000)
    assert s.peak_velocity_p90 == 5.0
    assert s.ppm == 1.0  # 1 punch in 1 minute
    assert s.duration_min == 1.0
    # score = 5.0 * (1/60) * 1 = 0.0833
    assert s.score == pytest.approx(0.083, abs=0.001)


def test_p90_caps_at_outliers() -> None:
    # 10 events: 9 around 3, one 100. p90 ignores the lone outlier.
    vels = [3.0] * 9 + [100.0]
    s = compute_score(vels, duration_ms=60_000)
    # p90 sits between 3.0 and 100.0 (90th percentile of n=10 is index ~8.1).
    assert 3.0 <= s.peak_velocity_p90 < 100.0


def test_score_scales_with_throughput_and_duration() -> None:
    # Same peak velocity, but session B is twice as long with twice the
    # punches → ppm identical → score scales linearly with duration.
    a = compute_score([4.0] * 60, duration_ms=60_000)
    b = compute_score([4.0] * 120, duration_ms=120_000)
    assert b.ppm == pytest.approx(a.ppm)
    assert b.score == pytest.approx(a.score * 2, rel=0.01)

"""compute_readiness — per-fighter z-score with cold-start fallback."""

from __future__ import annotations

import pytest

from analyze import MIN_HISTORY, compute_readiness


def test_cold_start_below_min_history_uses_absolute() -> None:
    r = compute_readiness(50.0, history_rmssd_ms=[40.0, 45.0])
    assert r.mode == "absolute"
    assert r.is_defensible is False
    assert r.history_n == 2
    # legacy: clamp((50-20)/70) * 100 = ~42
    assert 40 <= r.score <= 45


def test_z_score_kicks_in_at_min_history() -> None:
    history = [50.0, 52.0, 48.0, 51.0, 49.0]  # mean ~50, sd small
    assert len(history) == MIN_HISTORY
    r = compute_readiness(50.0, history)
    assert r.mode == "z_score"
    assert r.is_defensible is True
    # at the mean → z=0 → score=50
    assert r.score == 50
    assert r.baseline_mean_ms == pytest.approx(50.0)
    assert r.z == pytest.approx(0.0)


def test_z_score_one_sd_above_baseline() -> None:
    # history with mean=50, sd~3.16 (perfect square)
    history = [46.84, 53.16] + [50.0] * 4
    r = compute_readiness(history[0] + 2 * 3.16, history)  # +2 SD'ish
    assert r.mode == "z_score"
    assert r.score > 50  # better than typical


def test_z_score_well_above_clamps_at_100() -> None:
    history = [50.0] * 6 + [50.5] * 2
    r = compute_readiness(200.0, history)  # absurdly high
    assert r.mode == "z_score"
    assert r.score == 100


def test_z_score_well_below_clamps_at_0() -> None:
    history = [50.0, 51.0, 49.0, 50.5, 49.5, 50.2]
    r = compute_readiness(0.5, history)
    assert r.mode == "z_score"
    assert r.score == 0


def test_zero_variance_history_falls_back_to_absolute() -> None:
    # if all history values are identical, sd=0, no z-score possible
    r = compute_readiness(50.0, history_rmssd_ms=[50.0] * MIN_HISTORY)
    assert r.mode == "absolute"


def test_score_in_zero_to_hundred_inclusive() -> None:
    for hist_n in range(0, 12):
        r = compute_readiness(45.0, [40.0 + i for i in range(hist_n)])
        assert 0 <= r.score <= 100

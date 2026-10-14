"""HRV math unit tests — exact synthetic values, no hardware."""

from __future__ import annotations

import math
from uuid import uuid4

import pytest

from analyze import RollingHRMetrics, mean_hr_bpm, rmssd_ms, sdnn_ms
from contracts import HRSample


def _samples(rrs: list[float], session_id=None):  # type: ignore[no-untyped-def]
    sid = session_id or uuid4()
    out: list[HRSample] = []
    t = 0.0
    for rr in rrs:
        t += rr
        out.append(HRSample(session_id=sid, t_ms=t, rr_ms=rr, hr_bpm=60000.0 / rr))
    return out


def test_mean_hr_constant_rr_yields_constant_hr() -> None:
    s = _samples([1000.0, 1000.0, 1000.0])  # 60 bpm
    assert mean_hr_bpm(s) == pytest.approx(60.0)


def test_mean_hr_empty_is_zero() -> None:
    assert mean_hr_bpm([]) == 0.0


def test_rmssd_constant_rr_is_zero() -> None:
    s = _samples([800.0] * 10)
    assert rmssd_ms(s) == pytest.approx(0.0)


def test_rmssd_alternating_rr_matches_expected() -> None:
    # rr = [800, 820, 800, 820] → diffs = [20, -20, 20] → mean(d^2) = 400 → sqrt = 20
    s = _samples([800.0, 820.0, 800.0, 820.0])
    assert rmssd_ms(s) == pytest.approx(20.0)


def test_rmssd_single_sample_is_zero() -> None:
    s = _samples([800.0])
    assert rmssd_ms(s) == 0.0


def test_sdnn_constant_rr_is_zero() -> None:
    s = _samples([800.0] * 5)
    assert sdnn_ms(s) == pytest.approx(0.0)


def test_sdnn_known_values() -> None:
    # rr = [700, 800, 900], mean=800, variance (sample, n-1) = (10000+0+10000)/2 = 10000, sd=100
    s = _samples([700.0, 800.0, 900.0])
    assert sdnn_ms(s) == pytest.approx(100.0)


def test_rolling_window_evicts_old_samples() -> None:
    sid = uuid4()
    rolling = RollingHRMetrics(session_id=sid, window_ms=1500.0)
    # Samples at t=1000, 2000, 3000. At t=3000 the window is [1500, 3000].
    # The sample at t=1000 is older than 1500ms and must be evicted.
    s_in = _samples([1000.0, 1000.0, 1000.0], session_id=sid)
    final = None
    for s in s_in:
        final = rolling.feed(s)
    assert final is not None
    assert final.sample_count == 2
    assert final.window_start_ms == 2000.0
    assert final.window_end_ms == 3000.0
    assert final.mean_hr_bpm == pytest.approx(60.0)


def test_rolling_window_empty_snapshot() -> None:
    rolling = RollingHRMetrics(session_id=uuid4())
    snap = rolling.snapshot()
    assert snap.sample_count == 0
    assert snap.mean_hr_bpm == 0.0
    assert snap.rmssd_ms == 0.0
    assert snap.sdnn_ms == 0.0


def test_hr_sample_validation_rejects_zero_rr() -> None:
    from pydantic import ValidationError

    sid = uuid4()
    with pytest.raises(ValidationError):
        HRSample(session_id=sid, t_ms=0.0, rr_ms=0.0, hr_bpm=60.0)


def test_hr_sample_validation_rejects_unrealistic_hr() -> None:
    from pydantic import ValidationError

    sid = uuid4()
    with pytest.raises(ValidationError):
        HRSample(session_id=sid, t_ms=0.0, rr_ms=200.0, hr_bpm=400.0)


def test_full_metrics_chain_realistic_window() -> None:
    """Smoke test: 60s of RR data ~= 75 bpm with ±20ms jitter."""
    sid = uuid4()
    rolling = RollingHRMetrics(session_id=sid, window_ms=60_000.0)
    rrs = [800.0 + (10.0 if i % 2 == 0 else -10.0) for i in range(75)]
    snap = None
    for s in _samples(rrs, session_id=sid):
        snap = rolling.feed(s)
    assert snap is not None
    assert snap.sample_count == 75
    assert 70.0 <= snap.mean_hr_bpm <= 80.0
    assert math.isclose(snap.rmssd_ms, 20.0, rel_tol=0.01)


# ---- artifacts (ADR-037) ----

from analyze import clean_hrv  # noqa: E402

STEADY = [800.0, 820.0] * 30  # RMSSD 20 ms, 60 beats


def test_clean_beats_give_the_plain_figures() -> None:
    c = clean_hrv(STEADY)
    assert c.artifacts == 0 and c.reliable
    assert c.rmssd_ms == pytest.approx(20.0)
    assert c.mean_hr_bpm == pytest.approx(mean_hr_bpm(_samples(STEADY)))


def test_a_missed_beat_is_removed_and_not_bridged() -> None:
    rrs = [*STEADY[:30], 1620.0, *STEADY[30:]]  # one interval twice as long
    c = clean_hrv(rrs)
    assert c.artifacts == 1
    assert c.rmssd_ms == pytest.approx(20.0)
    assert rmssd_ms(_samples(rrs)) > 100  # raw: ~149 ms from one missed beat


def test_an_extra_beat_and_a_dropout_are_removed() -> None:
    rrs = [*STEADY[:20], 400.0, 410.0, *STEADY[20:40], 4000.0, *STEADY[40:]]
    c = clean_hrv(rrs)
    assert c.artifacts == 3
    assert c.rmssd_ms == pytest.approx(20.0)
    assert c.sdnn_ms == pytest.approx(sdnn_ms(_samples(STEADY)), rel=0.02)


def test_more_than_five_percent_artifacts_is_not_reliable() -> None:
    rrs = list(STEADY)
    for i in range(5, 60, 10):  # 6 of 60 = 10 %
        rrs[i] = 1600.0
    c = clean_hrv(rrs)
    assert c.artifacts == 6 and c.artifact_share == pytest.approx(0.1) and not c.reliable
    assert clean_hrv(STEADY[:1]).rmssd_ms is None and not clean_hrv([]).reliable


def test_a_real_change_in_heart_rate_is_kept() -> None:
    ramp = [1000.0 - 8.0 * i for i in range(60)]  # 60 → ~114 bpm, beat by beat
    assert clean_hrv(ramp).artifacts == 0


# ---- Lipponen–Tarvainen classes (ADR-040) ----

import numpy as np  # noqa: E402

from analyze.rr_artifacts import classify  # noqa: E402


def _natural(n: int, seed: int = 3) -> list[float]:
    """Resting-like RR: 900 ms with breathing (~0.25 Hz) and beat-to-beat noise."""
    rng = np.random.default_rng(seed)
    t = np.cumsum(np.full(n, 0.9))
    return list(900 + 40 * np.sin(2 * np.pi * 0.25 * t) + rng.normal(0, 12, n))


def test_natural_variability_is_left_alone() -> None:
    rrs = _natural(600)
    assert sum(label is not None for label in classify(rrs)) <= 3  # ≤ 0.5 %
    assert clean_hrv(rrs).reliable


def test_each_artifact_is_classed() -> None:
    rrs = _natural(300)
    rrs[50] = rrs[50] * 2  # a missed beat
    rrs[120:121] = [rrs[120] * 0.45, rrs[120] * 0.55]  # an extra beat splits one interval
    rrs[200], rrs[201] = rrs[200] * 0.7, rrs[201] * 1.3  # an ectopic beat and its pause
    labels = classify(rrs)
    assert labels[50] == "missed"
    assert labels[120] == "extra" and labels[121] == "extra"
    assert labels[200] is not None and labels[201] is not None
    assert sum(label is not None for label in labels) <= 7

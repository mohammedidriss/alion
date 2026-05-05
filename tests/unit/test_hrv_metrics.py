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

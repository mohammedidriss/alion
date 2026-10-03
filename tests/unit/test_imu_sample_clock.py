"""SampleClock — recovering true sample times from bursty BLE delivery."""

from __future__ import annotations

import random
from itertools import pairwise

import pytest

from capture.imu.clock import SampleClock


def _simulate(
    true_rate_hz: float, seconds: float, *, burst: int = 9, max_delay_s: float = 0.08, seed: int = 7
) -> tuple[list[float], list[float]]:
    """A sensor sampling at `true_rate_hz`, delivered in bursts with random BLE delay.

    Returns (true sample times, stamped sample times)."""
    rng = random.Random(seed)
    t0 = 1_790_000_000.0  # epoch-scale on purpose: guards float-precision handling
    period = 1.0 / true_rate_hz
    n = int(seconds * true_rate_hz)
    truth = [t0 + i * period for i in range(n)]
    clock = SampleClock(100.0)
    stamped: list[float] = []
    i = 0
    while i < n:
        count = min(burst + rng.randint(-3, 3), n - i)
        newest = truth[i + count - 1]
        arrival = newest + rng.uniform(0.002, max_delay_s)  # BLE only ever delays
        stamped.extend(clock.feed(arrival, count))
        i += count
    return truth, stamped


def test_bursty_stream_lands_on_the_true_grid() -> None:
    truth, stamped = _simulate(100.0, 60)
    errors_ms = [abs(s - t) * 1000 for s, t in zip(stamped, truth, strict=True)]
    settled = errors_ms[len(errors_ms) // 10 :]  # after a few seconds of fitting
    assert max(settled) < 5.0  # vs. up to 80 ms if stamped by arrival
    assert sum(settled) / len(settled) < 2.0


def test_tracks_crystal_drift() -> None:
    # A sensor running 0.03 % fast (300 ppm) — far worse than a real crystal.
    truth, stamped = _simulate(100.03, 120, seed=3)
    tail = [abs(s - t) * 1000 for s, t in zip(stamped[-500:], truth[-500:], strict=True)]
    assert max(tail) < 5.0  # nominal-rate stamping would be ~36 ms off by now


def test_timestamps_are_strictly_increasing() -> None:
    _, stamped = _simulate(100.0, 20)
    assert all(b > a for a, b in pairwise(stamped))


def test_period_starts_nominal_and_ignores_empty_feeds() -> None:
    clock = SampleClock(100.0)
    assert clock.period_s == pytest.approx(0.01)
    assert clock.feed(123.0, 0) == []
    out = clock.feed(123.0, 3)
    assert len(out) == 3 and clock.samples_seen == 3
    assert out[2] == pytest.approx(123.0)  # newest sample sits at its arrival time
    assert out[1] == pytest.approx(123.0 - 0.01)

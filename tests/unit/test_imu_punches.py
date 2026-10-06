"""IMU punch detector — synthetic wrist streams with punches at known times."""

from __future__ import annotations

import numpy as np

from analyze.imu_punches import detect_punches

RATE_HZ = 100.0


def _stream(
    seconds: float, punches_ms: list[float], *, peak_g: float = 6.0, seed: int = 1
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """A resting wrist (gravity on z, 0.05 g sensor noise) with a realistic burst per
    punch: launch, a bigger lock-out deceleration 120 ms later, then retraction."""
    rng = np.random.default_rng(seed)
    t = np.arange(0.0, seconds * 1000.0, 1000.0 / RATE_HZ)
    ax = rng.normal(0.0, 0.05, t.size)
    ay = rng.normal(0.0, 0.05, t.size)
    az = 1.0 + rng.normal(0.0, 0.05, t.size)
    for p in punches_ms:
        for offset, g, width in (
            (-120.0, 0.6 * peak_g, 25.0),
            (0.0, peak_g, 30.0),
            (180.0, 0.4 * peak_g, 40.0),
        ):
            ax += g * np.exp(-0.5 * ((t - (p + offset)) / width) ** 2)
    return t, ax, ay, az


def test_finds_each_punch_once_near_lock_out() -> None:
    truth = [1000.0, 2200.0, 3100.0, 4500.0, 5200.0]
    t, ax, ay, az = _stream(7, truth)
    found = detect_punches(t, ax, ay, az)
    assert len(found) == len(truth)  # launch + lock-out + retraction = one event
    for event, expected in zip(found, truth, strict=True):
        assert abs(event.t_ms - expected) <= 30.0  # far inside the ±200 ms match window
        assert event.peak_g > 4.0


def test_guard_shifts_and_footwork_are_not_punches() -> None:
    t, ax, ay, az = _stream(10, [], seed=2)
    # Slow guard adjustments / bouncing on the feet: ±0.6 g, 1–2 Hz.
    ax += 0.6 * np.sin(2 * np.pi * 1.5 * t / 1000.0)
    az += 0.4 * np.sin(2 * np.pi * 2.0 * t / 1000.0)
    assert detect_punches(t, ax, ay, az) == []


def test_a_fast_double_jab_counts_as_two() -> None:
    t, ax, ay, az = _stream(3, [1000.0, 1420.0])  # ~2.4 punches/s from one hand
    assert [round(e.t_ms, -1) for e in detect_punches(t, ax, ay, az)] == [1000.0, 1420.0]


def test_one_glitchy_sample_is_ignored() -> None:
    t, ax, ay, az = _stream(3, [])
    ax[150] += 8.0  # a single corrupted BLE sample, not a burst
    assert detect_punches(t, ax, ay, az) == []


def test_unsorted_input_and_tiny_streams() -> None:
    t, ax, ay, az = _stream(3, [1500.0])
    shuffle = np.random.default_rng(3).permutation(t.size)
    found = detect_punches(t[shuffle], ax[shuffle], ay[shuffle], az[shuffle])
    assert len(found) == 1 and abs(found[0].t_ms - 1500.0) <= 30.0
    assert detect_punches([0.0, 10.0], [0.0, 9.0], [0.0, 0.0], [1.0, 1.0]) == []


def _with_returns(punches_ms: list[float], *, return_after_ms: float = 430.0) -> tuple:
    """Uppercuts as seen on the first real take: each punch burst is followed
    ~430 ms later by an opposite, similar-sized burst as the fist returns to guard."""
    t, ax, ay, az = _stream(len(punches_ms) * 1.5 + 2, punches_ms)
    for p in punches_ms:
        ax -= 5.0 * np.exp(-0.5 * ((t - (p + return_after_ms)) / 35.0) ** 2)
    return t, ax, ay, az


def test_uppercut_return_to_guard_is_not_a_second_punch() -> None:
    from analyze.imu_punches import PROFILES

    truth = [1000.0, 2500.0, 4000.0]
    t, ax, ay, az = _with_returns(truth)
    assert len(detect_punches(t, ax, ay, az)) == 6  # the general detector counts the returns
    found = detect_punches(t, ax, ay, az, **PROFILES["uppercut"])
    assert [round(e.t_ms, -2) for e in found] == truth  # one per uppercut, on the punch


def test_hook_profile_finds_gentler_hooks() -> None:
    from analyze.imu_punches import PROFILES

    t, ax, ay, az = _stream(5, [1000.0, 2500.0], peak_g=2.2)  # 50 ms envelope ≈ 1.2 g
    assert detect_punches(t, ax, ay, az) == []  # under the general threshold
    found = detect_punches(t, ax, ay, az, **PROFILES["hook"])
    assert [round(e.t_ms, -2) for e in found] == [1000.0, 2500.0]


def test_first_mode_still_counts_a_double_jab_outside_the_gap() -> None:
    t, ax, ay, az = _stream(3, [1000.0, 1800.0])  # two real jabs 0.8 s apart
    found = detect_punches(t, ax, ay, az, mode="first", min_gap_ms=700.0)
    assert [round(e.t_ms, -2) for e in found] == [1000.0, 1800.0]

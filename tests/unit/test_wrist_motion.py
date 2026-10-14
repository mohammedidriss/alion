"""Wrist-only punch motion (ADR-028): the type features' window, and the speed
estimate on motion with a known answer."""

from __future__ import annotations

import numpy as np

from analyze import wrist_speed, wrist_types


def _stream(seconds: float = 2.0) -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(0.0, seconds * 1000.0, 10.0)
    imu = np.zeros((len(t), 6))
    imu[:, 2] = 1.0  # at rest: gravity on z
    return t, imu


def test_a_punch_window_sits_on_the_grid_with_the_punch_at_zero() -> None:
    t, imu = _stream()
    imu[(t >= 990) & (t <= 1010), 0] = 5.0  # the burst at 1 s
    win = wrist_types.window(t, imu, 1000.0)
    assert win is not None and win.shape == (len(wrist_types.GRID), 6)
    assert win[wrist_types.AT, 0] == 5.0
    row = wrist_types.features(win, "right")
    assert row.ndim == 1 and row[-1] == 1.0  # the hand flag
    assert np.all(np.isfinite(row))


def test_no_window_at_the_edges_or_across_a_dropout() -> None:
    t, imu = _stream()
    assert wrist_types.window(t, imu, 100.0) is None  # the launch is before the stream
    gap = (t < 900) | (t > 1100)
    assert wrist_types.window(t[gap], imu[gap], 1000.0) is None


def test_speed_is_the_integral_of_acceleration_after_gravity() -> None:
    t, imu = _stream()
    # Still for the first 100 ms of the window, then 2 g along x for 150 ms.
    imu[(t > 800) & (t <= 950), 0] = 2.0
    imu[:, 3] = 0.001  # a sensor that does send rotation (all-zero gyro means none)
    v = wrist_speed.peak_speed(t, imu[:, :3], imu[:, 3:], 960.0, before_ms=260.0)
    assert v is not None and abs(v - 2.0 * 9.80665 * 0.15) < 0.25  # ≈ 2.9 m/s


def test_no_speed_without_rotation_data() -> None:
    t, imu = _stream()
    assert wrist_speed.peak_speed(t, imu[:, :3], imu[:, 3:], 1000.0) is None

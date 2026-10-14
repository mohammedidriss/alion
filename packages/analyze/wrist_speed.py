"""A punch's hand speed estimated from one wrist sensor — research-grade.

The sensor measures acceleration (g) and rotation (°/s), not speed. Speed is the
integral of acceleration, after gravity is taken out — and gravity's direction in
the sensor's frame changes as the forearm turns. So, for each punch:

1. the launch window: `BEFORE_MS` before the burst's peak to the peak itself;
2. gravity: the mean acceleration over the window's first `REST_MS`, when the hand
   is still near guard (its direction in the sensor's frame at that moment);
3. the forearm's turn, from the gyro, keeps every later sample in that starting
   frame (rotation matrices, Rodrigues per 10 ms step);
4. speed: integrate (acceleration − gravity) × 9.81 from zero; the peak of |v|.

Integration drifts and the hand isn't perfectly still at the window's start, so
this is checked against the cameras' speed before anyone relies on it
(scripts/studies/wrist_speed_eval.py).
"""

from __future__ import annotations

import numpy as np

G = 9.80665
BEFORE_MS = 300.0  # the launch starts within this of the burst's peak
REST_MS = 40.0  # the window's first samples give gravity's direction
AFTER_MS = 20.0  # a little past the peak, where speed tops out at lock-out


def _rodrigues(w_rad: np.ndarray, dt: float) -> np.ndarray:
    angle = float(np.linalg.norm(w_rad)) * dt
    if angle < 1e-9:
        return np.eye(3)
    k = w_rad / np.linalg.norm(w_rad)
    kx = np.array([[0, -k[2], k[1]], [k[2], 0, -k[0]], [-k[1], k[0], 0]])
    r: np.ndarray = np.eye(3) + np.sin(angle) * kx + (1 - np.cos(angle)) * (kx @ kx)
    return r


def peak_speed(
    t_ms: np.ndarray,
    acc_g: np.ndarray,
    gyr_dps: np.ndarray,
    at_ms: float,
    *,
    before_ms: float = BEFORE_MS,
) -> float | None:
    """Estimated peak hand speed (m/s) of the punch whose burst peaks at `at_ms`,
    from one wrist's samples (`t_ms` sorted; `acc_g`, `gyr_dps` (n, 3)). None when
    the window has too few samples or no rotation data."""
    i0 = int(np.searchsorted(t_ms, at_ms - before_ms))
    i1 = int(np.searchsorted(t_ms, at_ms + AFTER_MS, side="right"))
    if i1 - i0 < 10 or not np.any(gyr_dps[i0:i1]):
        return None
    t = t_ms[i0:i1] / 1000.0
    a = acc_g[i0:i1]
    w = np.radians(gyr_dps[i0:i1])
    rest = t <= t[0] + REST_MS / 1000.0
    gravity = a[rest].mean(axis=0) if np.any(rest) else a[0]
    rot = np.eye(3)  # sensor frame now → the window's starting frame
    v = np.zeros(3)
    best = 0.0
    for k in range(1, len(t)):
        dt = float(t[k] - t[k - 1])
        if dt <= 0:
            continue
        rot = rot @ _rodrigues(w[k - 1], dt)
        lin = (rot @ a[k] - gravity) * G
        v = v + lin * dt
        best = max(best, float(np.linalg.norm(v)))
    return round(best, 2)

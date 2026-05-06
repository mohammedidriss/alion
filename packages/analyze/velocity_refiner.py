"""Sub-frame peak-velocity refinement for punch events.

The capture pipeline samples at the source's native rate (typically 30 fps =
~33ms between frames). Boxing punches peak in 50–100 ms — so a real peak
often falls *between* two captured frames and the discrete-frame velocity
underestimates the true peak by 10–25%.

This module fits a small smoothing curve (Catmull–Rom-style centered finite
difference over a 5-point window) to a wrist's recent positions and reports
the peak speed across the *continuous* fitted curve, evaluated at sub-frame
resolution.

It's a post-processor: takes a list of `(t_ms, x, y, z)` samples around a
detected punch and returns a refined peak m/s. Pure function, easy to test,
no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def refine_peak_velocity(
    samples: Sequence[tuple[float, float, float, float]],
    *,
    sub_steps: int = 5,
) -> float | None:
    """Return the peak speed in the same distance/time units as the samples.

    `samples` is a list of (t_ms, x, y, z) tuples in monotonically increasing
    time order. Need at least 4 points (3 segments) for a meaningful estimate.
    Each segment between consecutive samples is sub-sampled `sub_steps` times
    using a centered three-point velocity estimate at each fractional index.

    Returns the maximum estimated speed across all sub-steps, or None if there
    aren't enough samples.

    Distance is interpreted as Euclidean across the (x,y,z) components. Time is
    in milliseconds; the returned speed is units/second (m/s when fed metric
    world-landmark coords).
    """
    n = len(samples)
    if n < 4:
        return None
    # Convert to plain lists for fast indexed access.
    ts = [s[0] for s in samples]
    xs = [s[1] for s in samples]
    ys = [s[2] for s in samples]
    zs = [s[3] for s in samples]

    peak = 0.0
    # Walk each interior segment [i, i+1] and sample sub_steps points,
    # using a centered finite difference at each.
    for i in range(1, n - 2):
        for k in range(sub_steps):
            u = (k + 1) / (sub_steps + 1)  # 1/(N+1) .. N/(N+1), avoiding endpoints
            # Catmull–Rom interpolation between samples i and i+1 using i-1 and i+2 as tangents
            t = _interp_centered(ts, i, u)
            x = _interp_centered(xs, i, u)
            y = _interp_centered(ys, i, u)
            z = _interp_centered(zs, i, u)
            # Numerical derivative — sample a tiny step forward and compute speed.
            du = 0.05
            t2 = _interp_centered(ts, i, min(u + du, 0.999))
            x2 = _interp_centered(xs, i, min(u + du, 0.999))
            y2 = _interp_centered(ys, i, min(u + du, 0.999))
            z2 = _interp_centered(zs, i, min(u + du, 0.999))
            dt_s = max(1e-6, (t2 - t) / 1000.0)
            d = math.sqrt((x2 - x) ** 2 + (y2 - y) ** 2 + (z2 - z) ** 2)
            speed = d / dt_s
            if speed > peak:
                peak = speed
    return peak


def _interp_centered(values: list[float], i: int, u: float) -> float:
    """Centered Catmull–Rom interpolation over indices [i-1, i, i+1, i+2] at parameter u∈[0,1]."""
    p0 = values[i - 1]
    p1 = values[i]
    p2 = values[i + 1]
    p3 = values[i + 2]
    u2 = u * u
    u3 = u2 * u
    return 0.5 * (
        (2 * p1)
        + (-p0 + p2) * u
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u2
        + (-p0 + 3 * p1 - 3 * p2 + p3) * u3
    )

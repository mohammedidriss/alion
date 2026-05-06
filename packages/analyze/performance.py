"""Per-session performance score derived from CV punch events.

Transparent v1 formula — picked so the score moves the way a coach would
expect (faster + busier + longer = higher) without hidden weights:

    score = peak_velocity_p90 * (ppm / 60) * duration_min

Revisit once we have labeled training data; meanwhile this gives us a
single number per session for HRV-vs-performance scatter plots.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceScore:
    peak_velocity_p90: float
    ppm: float
    duration_min: float
    score: float


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def compute_score(velocities_ms: list[float], duration_ms: float) -> PerformanceScore:
    """Compute the v1 performance score.

    `velocities_ms`: peak velocity (m/s) of every detected punch.
    `duration_ms`: capture duration in milliseconds.
    """
    duration_min = (duration_ms / 1000.0) / 60.0 if duration_ms > 0 else 0.0
    n = len(velocities_ms)
    ppm = (n / duration_min) if duration_min > 0 else 0.0
    p90 = _percentile(sorted(velocities_ms), 0.9) if n else 0.0
    score = p90 * (ppm / 60.0) * duration_min
    return PerformanceScore(
        peak_velocity_p90=round(p90, 3),
        ppm=round(ppm, 2),
        duration_min=round(duration_min, 3),
        score=round(score, 3),
    )

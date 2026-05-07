"""Per-session performance score derived from CV punch events.

Transparent v1 formula — picked so the score moves the way a coach would
expect (faster + busier + longer = higher) without hidden weights:

    score = peak_velocity_p90 * (ppm / 60) * duration_min

Revisit once we have labeled training data; meanwhile this gives us a
single number per session for HRV-vs-performance scatter plots.

Also exposes Hopkins' Smallest Worthwhile Change (SWC) so the UI can
say "this session moved the needle" vs "this is within noise":

    SWC = 0.2 * stdev(history)

(Hopkins, *Sportscience* 2004; *Sports Medicine* 2009 vol. 39.)
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import stdev


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


def compute_swc(history: list[float]) -> float | None:
    """Hopkins' Smallest Worthwhile Change.

    Returns ``0.2 * stdev(history)`` — the minimum change that is unlikely
    to be noise. Returns None when history is too short (< 3) for a
    meaningful standard deviation.

    Strictly speaking Hopkins defines SWC against between-subject SD for
    a population. Within-fighter use here treats "between-session" SD as
    the relevant noise floor, which is the right shape for longitudinal
    monitoring of a single athlete.
    """
    if len(history) < 3:
        return None
    return round(0.2 * stdev(history), 4)


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

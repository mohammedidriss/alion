"""Internal training load metrics.

Banister TRIMP (Training Impulse) is a published, validated measure of
internal load — duration weighted by relative HR intensity. Cited in:

    Banister EW. *Modeling elite athletic performance.* In:
    Physiological Testing of the High-Performance Athlete (1991).

Computes ``duration_min × HR_ratio × y_factor`` where the y-factor is
Banister's exponentially-weighted intensity term, sex-specific:

    HR_ratio = (HR_avg − HR_rest) / (HR_max − HR_rest)
    y_male   = 0.64 · exp(1.92 · HR_ratio)
    y_female = 0.86 · exp(1.67 · HR_ratio)

The contract is wired now so the Polar H10 BLE driver can populate it
without code churn at hardware-arrival. Until live in-session HR
streams, callers will not have data to feed in (resting HR alone is
insufficient).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from math import exp
from typing import Literal

Sex = Literal["male", "female"]


@dataclass(frozen=True)
class TrimpResult:
    trimp: float
    duration_min: float
    hr_avg: float
    hr_ratio: float  # (HR_avg − HR_rest) / (HR_max − HR_rest), clamped 0..1
    n_samples: int


def estimate_hr_max(age_years: float) -> float:
    """Tanaka et al. 2001 — `208 − 0.7 × age`. More accurate than the
    legacy `220 − age` for adults, especially over 40."""
    return 208 - 0.7 * age_years


def compute_trimp(
    hr_samples_bpm: Iterable[float],
    *,
    duration_min: float,
    hr_rest_bpm: float,
    hr_max_bpm: float,
    sex: Sex = "male",
) -> TrimpResult | None:
    """Banister TRIMP. Returns None when inputs are insufficient."""
    samples = [s for s in hr_samples_bpm if s and s > 0]
    if not samples or duration_min <= 0 or hr_max_bpm <= hr_rest_bpm:
        return None
    hr_avg = sum(samples) / len(samples)
    raw_ratio = (hr_avg - hr_rest_bpm) / (hr_max_bpm - hr_rest_bpm)
    hr_ratio = max(0.0, min(1.0, raw_ratio))
    if sex == "female":
        y = 0.86 * exp(1.67 * hr_ratio)
    else:
        y = 0.64 * exp(1.92 * hr_ratio)
    trimp = duration_min * hr_ratio * y
    return TrimpResult(
        trimp=round(trimp, 3),
        duration_min=round(duration_min, 3),
        hr_avg=round(hr_avg, 2),
        hr_ratio=round(hr_ratio, 4),
        n_samples=len(samples),
    )

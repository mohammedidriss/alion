"""TRIMP (Banister) and SWC (Hopkins) — defensible load + change detection."""

from __future__ import annotations

import pytest

from analyze import compute_swc, compute_trimp, estimate_hr_max


# ---------- SWC (Smallest Worthwhile Change) ----------


def test_swc_returns_none_below_three_samples() -> None:
    assert compute_swc([]) is None
    assert compute_swc([1.0]) is None
    assert compute_swc([1.0, 2.0]) is None


def test_swc_is_zero_for_constant_history() -> None:
    assert compute_swc([2.0, 2.0, 2.0]) == 0.0


def test_swc_is_one_fifth_of_stdev() -> None:
    # stdev([1,2,3,4,5]) = sqrt(2.5) ≈ 1.5811; SWC ≈ 0.3162
    swc = compute_swc([1.0, 2.0, 3.0, 4.0, 5.0])
    assert swc is not None
    assert swc == pytest.approx(0.3162, abs=0.001)


# ---------- TRIMP ----------


def test_trimp_none_when_no_samples() -> None:
    assert (
        compute_trimp(
            [], duration_min=10.0, hr_rest_bpm=60, hr_max_bpm=190
        )
        is None
    )


def test_trimp_none_when_duration_zero() -> None:
    assert (
        compute_trimp(
            [120.0, 130.0],
            duration_min=0,
            hr_rest_bpm=60,
            hr_max_bpm=190,
        )
        is None
    )


def test_trimp_none_when_max_le_rest() -> None:
    assert (
        compute_trimp(
            [120.0],
            duration_min=10,
            hr_rest_bpm=190,
            hr_max_bpm=180,
        )
        is None
    )


def test_trimp_at_resting_hr_is_zero() -> None:
    """All samples at rest → ratio=0 → TRIMP=0."""
    r = compute_trimp(
        [60.0, 60.0],
        duration_min=10,
        hr_rest_bpm=60,
        hr_max_bpm=190,
    )
    assert r is not None
    assert r.trimp == 0.0


def test_trimp_increases_with_intensity() -> None:
    light = compute_trimp(
        [100.0] * 10, duration_min=20, hr_rest_bpm=60, hr_max_bpm=190
    )
    hard = compute_trimp(
        [170.0] * 10, duration_min=20, hr_rest_bpm=60, hr_max_bpm=190
    )
    assert light is not None and hard is not None
    assert hard.trimp > light.trimp


def test_trimp_increases_with_duration() -> None:
    short = compute_trimp(
        [140.0] * 5, duration_min=10, hr_rest_bpm=60, hr_max_bpm=190
    )
    long_ = compute_trimp(
        [140.0] * 5, duration_min=40, hr_rest_bpm=60, hr_max_bpm=190
    )
    assert short is not None and long_ is not None
    assert long_.trimp == pytest.approx(short.trimp * 4, rel=0.01)


def test_trimp_male_vs_female_at_same_intensity() -> None:
    male = compute_trimp(
        [150.0] * 5, duration_min=20, hr_rest_bpm=60, hr_max_bpm=190, sex="male"
    )
    female = compute_trimp(
        [150.0] * 5,
        duration_min=20,
        hr_rest_bpm=60,
        hr_max_bpm=190,
        sex="female",
    )
    assert male is not None and female is not None
    # Different curves; just check both produced sensible non-zero values.
    assert male.trimp > 0
    assert female.trimp > 0


def test_trimp_clamps_supraphysiological_ratio() -> None:
    """HR above the max shouldn't blow the formula — clamp at 1.0."""
    r = compute_trimp(
        [250.0],  # above the assumed max
        duration_min=10,
        hr_rest_bpm=60,
        hr_max_bpm=190,
    )
    assert r is not None
    assert r.hr_ratio == 1.0


# ---------- HR_max estimator ----------


def test_estimate_hr_max_tanaka() -> None:
    # Tanaka et al.: 208 - 0.7 * age
    assert estimate_hr_max(25) == pytest.approx(208 - 0.7 * 25)
    assert estimate_hr_max(40) == pytest.approx(208 - 0.7 * 40)

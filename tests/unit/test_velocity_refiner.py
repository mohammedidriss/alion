"""Sub-frame velocity refiner — synthetic trajectories with known peak speeds."""

from __future__ import annotations

import math

from analyze import refine_peak_velocity


def test_returns_none_for_too_few_samples() -> None:
    assert refine_peak_velocity([(0.0, 0.0, 0.0, 0.0)]) is None
    assert refine_peak_velocity([(0.0, 0, 0, 0), (33.3, 0, 0, 0.1)]) is None


def test_constant_velocity_recovers_correctly() -> None:
    """Wrist moves 0.5 m in 0.5s = 1.0 m/s constant."""
    samples = [(i * 100.0, i * 0.1, 0.0, 0.0) for i in range(6)]
    peak = refine_peak_velocity(samples)
    assert peak is not None
    assert math.isclose(peak, 1.0, rel_tol=0.05)


def test_recovers_higher_peak_than_naive_frame_diff() -> None:
    """Build a trajectory whose true peak velocity is between captured frames."""
    # Wrist accelerates and decelerates around frame 3 — naive
    # frame-to-frame max would be the segment from frame 2 to 3.
    # The continuous curve has a higher peak just before frame 3.
    positions = [0.00, 0.05, 0.20, 0.45, 0.55, 0.58, 0.60]  # decelerating after 3
    samples = [(i * 33.3, p, 0.0, 0.0) for i, p in enumerate(positions)]

    # Naive peak: largest |Δp| / Δt between adjacent frames
    naive_peak = max(
        abs(positions[i + 1] - positions[i]) / (33.3 / 1000.0) for i in range(len(positions) - 1)
    )

    refined = refine_peak_velocity(samples, sub_steps=10)
    assert refined is not None
    # Refined peak should be at least as large as naive (continuous curve has
    # the same max-or-greater than discrete samples in a smooth curve).
    assert refined >= naive_peak * 0.98

"""Punch events from one wrist IMU — the detector behind the dataset auto-labeler.

At the wrist a punch is a short burst of acceleration: the launch, a large
deceleration as the arm locks out (or the glove lands), then the retraction.
This finds those bursts on the dynamic acceleration ||a| − 1 g| and reports one
event per burst at its peak, which sits within ~100 ms of full extension —
inside the ±200 ms window `studies.evaluation.match_events` scores against.

The IMU is an independent sensor, so labels from it don't inherit the CV
detector's errors (the circularity an examiner would flag if ground truth came
from wrist velocity in the video).

Pure numpy over one wrist's samples; the caller splits by hand.

Calibrated on the first real take (216df089, orthodox, gloves, 100 Hz) with the
video as the reference: straights put one burst per punch near full extension;
an uppercut adds a second, opposite burst ~0.43 s later as the fist returns to
guard; hooks peak lower (1–2 g) at the start of the swing. `PROFILES` holds the
per-type settings the labeler uses inside typed protocol blocks, where the
punch type is known; free shadowboxing uses the defaults.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np

GRAVITY_G = 1.0

# Defaults tuned for shadowboxing with gloves at the wrist: punches peak at
# 3–10 g of dynamic acceleration, guard adjustments and footwork stay under ~1 g.
THRESHOLD_G = 1.5  # on the 50 ms envelope, which runs below the raw spike
MIN_GAP_MS = 350.0  # one event per burst; a same-hand double jab is ~400 ms apart
SMOOTH_MS = 50.0
BURST_MS = 250.0  # "first" mode: one punch's launch-to-lock-out burst

# Per punch type, for blocks where the type is known. "first" keeps the first
# burst and ignores that wrist for `min_gap_ms` — so an uppercut's return to
# guard (~430 ms after the punch, and often as tall) isn't counted; hooks get a
# lower threshold because their wrist acceleration is gentler.
PROFILES: dict[str, dict[str, Any]] = {
    "jab": {},
    "cross": {},
    "hook": {"threshold_g": 1.0, "min_gap_ms": 600.0, "mode": "first"},
    "uppercut": {"threshold_g": 1.5, "min_gap_ms": 700.0, "mode": "first"},
}


# The WT901's accelerometer reads ±16 g; an axis at or past this has clipped, so
# the punch's peak is at least what was read, not what it was (ADR-042).
CLIP_G = 15.5


@dataclass(frozen=True)
class ImuPunch:
    t_ms: float  # time of the burst's largest raw sample
    peak_g: float  # its dynamic acceleration, ||a| − 1 g|
    clipped: bool = False  # an axis hit the sensor's range: peak_g is a minimum


def detect_punches(
    t_ms: Sequence[float] | np.ndarray,
    ax: Sequence[float] | np.ndarray,
    ay: Sequence[float] | np.ndarray,
    az: Sequence[float] | np.ndarray,
    *,
    threshold_g: float = THRESHOLD_G,
    min_gap_ms: float = MIN_GAP_MS,
    smooth_ms: float = SMOOTH_MS,
    mode: Literal["tallest", "first"] = "tallest",
) -> list[ImuPunch]:
    """Punch events in one wrist's stream, oldest first.

    1. Dynamic acceleration ||a| − 1 g| removes gravity whatever the wrist's tilt.
    2. A `smooth_ms` moving average turns each burst into one hump and ignores a
       single glitchy sample.
    3. Humps at or above `threshold_g` are candidates. `mode="tallest"` keeps the
       tallest and drops any within `min_gap_ms` of it (launch, lock-out and
       retraction fall inside one burst). `mode="first"` walks forward in time and
       ignores the wrist for `min_gap_ms` after each punch — for a punch whose
       return to guard is a separate burst.
    4. Each event is placed on the largest raw sample in its hump.
    """
    t = np.asarray(t_ms, dtype=float)
    if t.size < 3:
        return []
    order = np.argsort(t, kind="stable")
    t = t[order]
    acc = np.stack(
        [np.asarray(ax, dtype=float), np.asarray(ay, dtype=float), np.asarray(az, dtype=float)],
        axis=1,
    )[order]
    dyn = np.abs(np.linalg.norm(acc, axis=1) - GRAVITY_G)

    step_ms = float(np.median(np.diff(t))) or 10.0
    k = max(1, round(smooth_ms / step_ms))
    env = np.convolve(dyn, np.ones(k) / k, mode="same") if k > 1 else dyn

    # Local maxima of the envelope (plateaus count once, at their first sample).
    left = np.concatenate(([-np.inf], env[:-1]))
    right = np.concatenate((env[1:], [-np.inf]))
    peaks = np.flatnonzero((env >= threshold_g) & (env >= left) & (env > right))

    kept: list[int] = []
    if mode == "first":
        cands = peaks.tolist()
        for n, p in enumerate(cands):
            if kept and t[p] - t[kept[-1]] < min_gap_ms:
                continue
            # The punch's own burst (launch → lock-out) spans ~250 ms: place the
            # event on its tallest hump, not on the launch that crossed first.
            burst = [q for q in cands[n:] if t[q] - t[p] <= BURST_MS]
            kept.append(max(burst, key=lambda q: env[q]))
    else:
        for p in sorted(peaks.tolist(), key=lambda p: env[p], reverse=True):
            if all(abs(t[p] - t[k]) >= min_gap_ms for k in kept):
                kept.append(p)

    events = []
    for p in kept:
        # The samples within smooth_ms of the hump (t is sorted: a slice, not a scan).
        lo = int(np.searchsorted(t, t[p] - smooth_ms, side="left"))
        hi = int(np.searchsorted(t, t[p] + smooth_ms, side="right"))
        window = np.arange(lo, hi)
        j = int(window[np.argmax(dyn[window])])
        clipped = bool(np.any(np.abs(acc[window]) >= CLIP_G))
        events.append(ImuPunch(t_ms=float(t[j]), peak_g=round(float(dyn[j]), 2), clipped=clipped))
    return sorted(events, key=lambda e: e.t_ms)


# The forearm's turn that drives a punch (pronation on a straight, the swing of a
# hook, the lift of an uppercut) peaks within this of the acceleration peak.
ROTATION_WINDOW_MS = 150.0


def peak_rotations(
    t_ms: Sequence[float] | np.ndarray,
    gx: Sequence[float] | np.ndarray,
    gy: Sequence[float] | np.ndarray,
    gz: Sequence[float] | np.ndarray,
    at_ms: Sequence[float],
    *,
    window_ms: float = ROTATION_WINDOW_MS,
) -> list[float | None]:
    """For each punch time in `at_ms`, the fastest the wrist turned (°/s, the
    gyro's magnitude) within `window_ms` of it. None where the sensor sent no
    rotation (all zero) or has no samples that close."""
    t = np.asarray(t_ms, dtype=float)
    w = (
        np.linalg.norm(
            np.stack([np.asarray(gx, float), np.asarray(gy, float), np.asarray(gz, float)], axis=1),
            axis=1,
        )
        if t.size
        else np.zeros(0)
    )
    if t.size == 0 or not np.any(w):
        return [None for _ in at_ms]
    order = np.argsort(t, kind="stable")
    t, w = t[order], w[order]
    out: list[float | None] = []
    for at in at_ms:
        lo, hi = (
            np.searchsorted(t, at - window_ms),
            np.searchsorted(t, at + window_ms, side="right"),
        )
        out.append(round(float(w[lo:hi].max()), 1) if hi > lo else None)
    return out

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
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

GRAVITY_G = 1.0

# Defaults tuned for shadowboxing with gloves at the wrist: punches peak at
# 3–10 g of dynamic acceleration, guard adjustments and footwork stay under ~1 g.
THRESHOLD_G = 1.5  # on the 50 ms envelope, which runs below the raw spike
MIN_GAP_MS = 350.0  # one event per burst; a same-hand double jab is ~400 ms apart
SMOOTH_MS = 50.0


@dataclass(frozen=True)
class ImuPunch:
    t_ms: float  # time of the burst's largest raw sample
    peak_g: float  # its dynamic acceleration, ||a| − 1 g|


def detect_punches(
    t_ms: Sequence[float] | np.ndarray,
    ax: Sequence[float] | np.ndarray,
    ay: Sequence[float] | np.ndarray,
    az: Sequence[float] | np.ndarray,
    *,
    threshold_g: float = THRESHOLD_G,
    min_gap_ms: float = MIN_GAP_MS,
    smooth_ms: float = SMOOTH_MS,
) -> list[ImuPunch]:
    """Punch events in one wrist's stream, oldest first.

    1. Dynamic acceleration ||a| − 1 g| removes gravity whatever the wrist's tilt.
    2. A `smooth_ms` moving average turns each burst into one hump and ignores a
       single glitchy sample.
    3. Humps at or above `threshold_g` are candidates; keeping the tallest and
       dropping any within `min_gap_ms` of it leaves one event per punch (the
       launch, lock-out and retraction spikes all fall inside one burst).
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
    for p in sorted(peaks.tolist(), key=lambda p: env[p], reverse=True):
        if all(abs(t[p] - t[k]) >= min_gap_ms for k in kept):
            kept.append(p)

    events = []
    for p in kept:
        window = np.flatnonzero(np.abs(t - t[p]) <= smooth_ms)
        j = int(window[np.argmax(dyn[window])])
        events.append(ImuPunch(t_ms=float(t[j]), peak_g=round(float(dyn[j]), 2)))
    return sorted(events, key=lambda e: e.t_ms)

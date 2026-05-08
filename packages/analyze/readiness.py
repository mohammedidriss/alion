"""Readiness — defensible, per-fighter HRV-based score.

The previous formula was `clamp((RMSSD - 20) / 70)` — a single linear remap
applied identically to every fighter regardless of age, sex, training state
or baseline. Resting RMSSD is known to vary by an order of magnitude across
populations, so a universal cutoff mislabels most individuals in known-biased
ways. This module replaces that with a per-fighter z-score against the
fighter's own rolling history, with an honest cold-start fallback.

Formula:
    z = (rmssd - mean(history)) / stdev(history)   # if N(history) >= 5
    score = clamp(50 + 12.5 * z, 0, 100)
        # +1 SD ≈ 62.5, -1 SD ≈ 37.5, +4 SD = 100, -4 SD = 0
        # Centred on 50 so "today vs my normal" is the readable axis.

Cold-start (N < 5):
    Fall back to the legacy linear remap, but tag the result so the UI can
    display "absolute" vs "z-score" mode honestly.

This is not a clinical readiness score. It is a per-fighter relative
indicator. The dissertation should describe it as such.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, stdev
from typing import Literal

ReadinessMode = Literal["absolute", "z_score"]
"""How the score was computed.

- "absolute": legacy linear remap clamp((rmssd-20)/70). Used when the
  fighter has fewer than `MIN_HISTORY` recorded baselines.
- "z_score": per-fighter z-score against history. Defensible for a
  fighter with >= MIN_HISTORY baselines.
"""

MIN_HISTORY = 5  # Below this, z-score is unstable; fall back to absolute.


@dataclass(frozen=True)
class Readiness:
    score: int  # 0-100
    mode: ReadinessMode
    rmssd_ms: float
    history_n: int
    baseline_mean_ms: float | None = None  # None for absolute mode
    baseline_sd_ms: float | None = None
    z: float | None = None

    @property
    def is_defensible(self) -> bool:
        """True when the score is computed from sufficient per-fighter
        history. Use for UI gating (e.g. show 'calibrated' badge)."""
        return self.mode == "z_score"


def compute_readiness(rmssd_ms: float, history_rmssd_ms: list[float]) -> Readiness:
    """Compute a readiness score from the fighter's latest RMSSD and history.

    `history_rmssd_ms` should NOT include the current measurement.
    """
    n = len(history_rmssd_ms)
    if n >= MIN_HISTORY:
        m = mean(history_rmssd_ms)
        sd = stdev(history_rmssd_ms)
        if sd > 0:
            z = (rmssd_ms - m) / sd
            score = max(0, min(100, round(50 + 12.5 * z)))
            return Readiness(
                score=score,
                mode="z_score",
                rmssd_ms=rmssd_ms,
                history_n=n,
                baseline_mean_ms=round(m, 2),
                baseline_sd_ms=round(sd, 2),
                z=round(z, 2),
            )
    # Cold-start fallback — clearly tagged so UI can warn.
    score = max(0, min(100, round(((rmssd_ms - 20.0) / 70.0) * 100)))
    return Readiness(
        score=score,
        mode="absolute",
        rmssd_ms=rmssd_ms,
        history_n=n,
    )

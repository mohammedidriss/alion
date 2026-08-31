"""rPPG pulse estimation — POS projection + band-pass + peak detection (ADR 008).

Pure signal processing over an RGB trace (per-frame mean colour of a skin ROI).
No I/O, no session/clock context — the source layer supplies those. numpy is
lazy-imported so the module loads on machines without it.

Pipeline (Wang et al. 2017, POS, single-window simplification):

1. Temporally normalise the three channels.
2. Project to a pulse signal via the POS matrix.
3. Band-pass to the plausible pulse band (0.7-4.0 Hz ≈ 42-240 bpm) via FFT.
4. Detect peaks → beat times → inter-beat intervals (IBIs).
5. Quality = fraction of spectral power inside the pulse band (an SNR proxy);
   rPPG is motion/light-sensitive, so this gates trust downstream.

The IBIs here are pulse-rate variability (PRV), NOT ECG RR intervals — see
ADR 008. Kept deliberately separate from the HRV pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

# Plausible human pulse band.
_LO_HZ = 0.7  # 42 bpm
_HI_HZ = 4.0  # 240 bpm
# IBIs outside this range are treated as detection noise and dropped.
_MIN_IBI_MS = 250.0  # 240 bpm
_MAX_IBI_MS = 2000.0  # 30 bpm
_EPS = 1e-9

RgbTrace = Sequence[tuple[float, float, float]]


@dataclass(frozen=True)
class PulseWindow:
    """Result of estimating pulse over one low-motion window.

    `beats_ms` and `ibis_ms` are aligned and equal length: `ibis_ms[i]` is the
    inter-beat interval that *closes* at `beats_ms[i]` (i.e. the interval from the
    previous beat). Only physiologically plausible intervals are kept, so the two
    tuples stay in lock-step. `mean_bpm` is derived from the median IBI;
    `quality` is 0-1.
    """

    beats_ms: tuple[float, ...]
    ibis_ms: tuple[float, ...]
    mean_bpm: float
    quality: float

    @classmethod
    def empty(cls) -> PulseWindow:
        return cls(beats_ms=(), ibis_ms=(), mean_bpm=0.0, quality=0.0)


def estimate_pulse(rgb_trace: RgbTrace, fps: float) -> PulseWindow:
    """Estimate beats + IBIs + quality from an RGB trace. Pure function."""
    import numpy as np

    if fps <= 0:
        return PulseWindow.empty()
    c = np.asarray(rgb_trace, dtype=np.float64)
    # Need at least ~2 seconds to resolve the lowest plausible pulse.
    if c.ndim != 2 or c.shape[1] != 3 or c.shape[0] < max(8, int(2 * fps)):
        return PulseWindow.empty()

    pulse = _pos_project(c)
    banded, quality = _bandpass_and_quality(pulse, fps)

    min_dist = max(1, int(0.25 * fps))  # ≥250 ms between beats
    peak_idx = _find_peaks(banded, min_dist)
    if peak_idx.size < 2:
        return PulseWindow.empty()

    all_beats_ms = peak_idx.astype(np.float64) / fps * 1000.0
    all_ibis = np.diff(all_beats_ms)  # all_ibis[i] closes at all_beats_ms[i + 1]
    plausible = (all_ibis >= _MIN_IBI_MS) & (all_ibis <= _MAX_IBI_MS)
    ibis = all_ibis[plausible]
    closing_beats = all_beats_ms[1:][plausible]  # kept aligned with `ibis`
    if ibis.size == 0:
        return PulseWindow.empty()

    mean_bpm = float(60_000.0 / np.median(ibis))
    return PulseWindow(
        beats_ms=tuple(float(x) for x in closing_beats),
        ibis_ms=tuple(float(x) for x in ibis),
        mean_bpm=mean_bpm,
        quality=quality,
    )


def _pos_project(c: Any) -> Any:
    """POS (plane-orthogonal-to-skin) projection → 1-D pulse signal."""
    import numpy as np

    mean = c.mean(axis=0)
    mean[mean == 0] = _EPS
    cn = (c / mean).T  # (3, N), temporally normalised
    proj = np.array([[0.0, 1.0, -1.0], [-2.0, 1.0, 1.0]])
    s = proj @ cn  # (2, N)
    alpha = float(s[0].std()) / (float(s[1].std()) + _EPS)
    h = s[0] + alpha * s[1]
    return h - h.mean()


def _bandpass_and_quality(pulse: Any, fps: float) -> tuple[Any, float]:
    """Zero out-of-band FFT bins; return (band-passed signal, in-band power ratio)."""
    import numpy as np

    n = pulse.shape[0]
    freqs = np.fft.rfftfreq(n, d=1.0 / fps)
    spectrum = np.fft.rfft(pulse)
    band = (freqs >= _LO_HZ) & (freqs <= _HI_HZ)
    power = np.abs(spectrum) ** 2
    total = float(power.sum())
    quality = float(power[band].sum() / (total + _EPS)) if total > 0 else 0.0
    banded = np.fft.irfft(spectrum * band, n=n)
    return banded, min(1.0, max(0.0, quality))


def _find_peaks(x: Any, min_dist: int) -> Any:
    """Local maxima above zero, at least `min_dist` samples apart."""
    import numpy as np

    peaks: list[int] = []
    last = -min_dist
    for i in range(1, x.shape[0] - 1):
        if x[i] > x[i - 1] and x[i] >= x[i + 1] and x[i] > 0 and (i - last) >= min_dist:
            peaks.append(i)
            last = i
    return np.asarray(peaks, dtype=np.int64)

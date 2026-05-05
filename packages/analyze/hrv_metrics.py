"""HRV math: mean HR, RMSSD, SDNN, plus a rolling-window aggregator.

Pure functions. No I/O, no state outside the rolling-window class.

Definitions (these are the standard time-domain HRV metrics):
- mean HR = mean(60000 / rr_ms_i) over window
- RMSSD   = sqrt(mean((rr_i - rr_{i-1})^2)) — sensitive to short-term variability
- SDNN   = sample standard deviation of rr_ms over the window

Implemented without numpy because the per-window math is small and we'd
rather keep the math visible than push it through a black-box dependency.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable
from uuid import UUID

from contracts import HRMetricsWindow, HRSample


def mean_hr_bpm(samples: Iterable[HRSample]) -> float:
    rrs = [s.rr_ms for s in samples]
    if not rrs:
        return 0.0
    return sum(60000.0 / rr for rr in rrs) / len(rrs)


def rmssd_ms(samples: Iterable[HRSample]) -> float:
    """Root mean square of successive RR-interval differences."""
    rrs = [s.rr_ms for s in samples]
    if len(rrs) < 2:
        return 0.0
    diffs = [rrs[i] - rrs[i - 1] for i in range(1, len(rrs))]
    mean_sq = sum(d * d for d in diffs) / len(diffs)
    return math.sqrt(mean_sq)


def sdnn_ms(samples: Iterable[HRSample]) -> float:
    """Sample standard deviation of RR intervals."""
    rrs = [s.rr_ms for s in samples]
    n = len(rrs)
    if n < 2:
        return 0.0
    mean = sum(rrs) / n
    variance = sum((rr - mean) ** 2 for rr in rrs) / (n - 1)
    return math.sqrt(variance)


class RollingHRMetrics:
    """Maintains a sliding window of recent HR samples and emits HRMetricsWindow."""

    def __init__(self, session_id: UUID, window_ms: float = 60_000.0) -> None:
        self.session_id = session_id
        self.window_ms = window_ms
        self._samples: deque[HRSample] = deque()

    def feed(self, sample: HRSample) -> HRMetricsWindow:
        """Add a sample, evict any older than the window, return current metrics."""
        self._samples.append(sample)
        cutoff = sample.t_ms - self.window_ms
        while self._samples and self._samples[0].t_ms < cutoff:
            self._samples.popleft()
        return self._snapshot()

    def snapshot(self) -> HRMetricsWindow:
        return self._snapshot()

    def _snapshot(self) -> HRMetricsWindow:
        if not self._samples:
            return HRMetricsWindow(
                session_id=self.session_id,
                window_start_ms=0.0,
                window_end_ms=0.0,
                sample_count=0,
                mean_hr_bpm=0.0,
                rmssd_ms=0.0,
                sdnn_ms=0.0,
            )
        return HRMetricsWindow(
            session_id=self.session_id,
            window_start_ms=self._samples[0].t_ms,
            window_end_ms=self._samples[-1].t_ms,
            sample_count=len(self._samples),
            mean_hr_bpm=round(mean_hr_bpm(self._samples), 2),
            rmssd_ms=round(rmssd_ms(self._samples), 2),
            sdnn_ms=round(sdnn_ms(self._samples), 2),
        )

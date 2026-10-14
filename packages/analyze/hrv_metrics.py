"""HRV math: mean HR, RMSSD, SDNN, plus a rolling-window aggregator.

Pure functions. No I/O, no state outside the rolling-window class.

Definitions (these are the standard time-domain HRV metrics):
- mean HR = mean(60000 / rr_ms_i) over window
- RMSSD   = sqrt(mean((rr_i - rr_{i-1})^2)) — sensitive to short-term variability
- SDNN   = sample standard deviation of rr_ms over the window

Implemented without numpy because the per-window math is small and we'd
rather keep the math visible than push it through a black-box dependency.

The three functions take the beats as given. `clean_hrv` removes artifacts first
(ADR-037) — what every stored, live and uploaded figure goes through:
- outside 30–200 bpm (300–2000 ms): a dropout or noise, not a heartbeat;
- more than 20 % from the median of up to 5 beats on each side: a missed beat
  (one interval twice as long) or an extra one (two short ones);
- RMSSD only from differences between two kept, consecutive beats — never
  across a removed one; SDNN and mean HR from the kept beats;
- more than 5 % of beats removed: the HRV isn't reliable (`reliable` False).
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
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


RR_MIN_MS, RR_MAX_MS = 300.0, 2000.0  # 200 and 30 bpm
MAX_DEVIATION = 0.20  # from the local median
NEIGHBOURS = 5  # beats on each side for that median
MAX_ARTIFACT_SHARE = 0.05  # above this, HRV from these beats isn't reliable


def artifact_mask(rrs: Sequence[float]) -> list[bool]:
    """True for each interval that is an artifact, not a heartbeat."""
    n = len(rrs)
    in_range = [RR_MIN_MS <= r <= RR_MAX_MS for r in rrs]
    bad = [not ok for ok in in_range]
    for i in range(n):
        if bad[i]:
            continue
        ref = [
            rrs[j]
            for j in range(max(0, i - NEIGHBOURS), min(n, i + NEIGHBOURS + 1))
            if j != i and in_range[j]
        ]
        if len(ref) >= 2:
            med = statistics.median(ref)
            bad[i] = abs(rrs[i] - med) > MAX_DEVIATION * med
    return bad


@dataclass(frozen=True)
class CleanHRV:
    beats: int  # every interval given
    artifacts: int  # removed
    mean_hr_bpm: float | None  # None: no beat kept
    rmssd_ms: float | None  # None: no two consecutive beats kept
    sdnn_ms: float | None  # None: fewer than two beats kept

    @property
    def artifact_share(self) -> float:
        return self.artifacts / self.beats if self.beats else 0.0

    @property
    def reliable(self) -> bool:
        return self.rmssd_ms is not None and self.artifact_share <= MAX_ARTIFACT_SHARE


def clean_hrv(rrs: Sequence[float]) -> CleanHRV:
    """Mean HR, RMSSD and SDNN from RR intervals in time order, artifacts removed."""
    bad = artifact_mask(rrs)
    kept = [r for r, b in zip(rrs, bad, strict=True) if not b]
    diffs = [rrs[i] - rrs[i - 1] for i in range(1, len(rrs)) if not bad[i] and not bad[i - 1]]
    return CleanHRV(
        beats=len(rrs),
        artifacts=sum(bad),
        mean_hr_bpm=sum(60000.0 / r for r in kept) / len(kept) if kept else None,
        rmssd_ms=math.sqrt(sum(d * d for d in diffs) / len(diffs)) if diffs else None,
        sdnn_ms=statistics.stdev(kept) if len(kept) >= 2 else None,
    )


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
        c = clean_hrv([s.rr_ms for s in self._samples])
        return HRMetricsWindow(
            session_id=self.session_id,
            window_start_ms=self._samples[0].t_ms,
            window_end_ms=self._samples[-1].t_ms,
            sample_count=len(self._samples),
            mean_hr_bpm=round(c.mean_hr_bpm or 0.0, 2),
            rmssd_ms=round(c.rmssd_ms or 0.0, 2),
            sdnn_ms=round(c.sdnn_ms or 0.0, 2),
        )

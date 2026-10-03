"""Timestamps for a fixed-rate sensor whose samples arrive in bursty BLE notifications.

The WT901 samples at a steady internal rate (100 Hz), but macOS delivers them in
bursts — measured gaps of ~90 ms with no loss. Stamping each sample with its
*arrival* time would smear punch timing by up to a burst. Instead each sample is
placed on the sensor's own grid:

    t(i) = anchor + i · period

BLE can only *delay* a sample, never deliver it early, so the useful signal is
the **lower envelope** of arrivals — the fastest deliveries:

* **period** — nominal, corrected by the slope of the per-block minimum residual
  (one fastest arrival per 5 s block). Fitting minima rather than every noisy
  arrival is far more precise, and it tracks crystal drift.
* **anchor** — the minimum of ``arrival − index · period`` over a recent window.
* **monotonic** — when a better (earlier) anchor is found, output slews toward it
  at 90 % sample spacing instead of stepping backwards, so stored timestamps
  always increase.

Pure Python (no Bluetooth), so it is unit-tested with simulated burst streams.
"""

from __future__ import annotations

from collections import deque

_SLEW = 0.9  # minimum spacing while catching up to a corrected anchor, as a fraction of a period


class SampleClock:
    """Assigns wall-clock times to samples from one fixed-rate sensor connection."""

    def __init__(
        self,
        rate_hz: float,
        *,
        window: int = 200,
        block_s: float = 5.0,
        max_skew: float = 1e-3,
    ) -> None:
        self._nominal = 1.0 / rate_hz
        self._block = max(1, round(block_s * rate_hz))
        self._max_skew = max_skew
        self._hist: deque[tuple[int, float]] = deque(maxlen=window)  # recent (index, arrival)
        self._minima: deque[tuple[int, float]] = deque(maxlen=120)  # per-block (index, residual)
        self._cur: tuple[int, int, float] | None = None  # (block no, index, residual)
        self._n = 0  # samples seen so far = index of the next sample
        self._y0: float | None = None  # first arrival, subtracted for float precision
        self._last: float | None = None  # last emitted time (relative to _y0)

    @property
    def samples_seen(self) -> int:
        return self._n

    @property
    def period_s(self) -> float:
        """Nominal period, drift-corrected once three blocks of minima exist."""
        pts = list(self._minima)
        if len(pts) < 3:
            return self._nominal
        k = len(pts)
        sx = sum(i for i, _ in pts)
        sy = sum(r for _, r in pts)
        sxx = sum(i * i for i, _ in pts)
        sxy = sum(i * r for i, r in pts)
        den = k * sxx - sx * sx
        if den <= 0:
            return self._nominal
        drift = (k * sxy - sx * sy) / den  # seconds per sample relative to nominal
        bound = self._nominal * self._max_skew
        return self._nominal + min(max(drift, -bound), bound)

    def feed(self, arrival_s: float, count: int) -> list[float]:
        """Register a notification carrying `count` samples that arrived at `arrival_s`
        (wall-clock seconds). Returns one wall-clock time (seconds) per sample."""
        if count <= 0:
            return []
        if self._y0 is None:
            self._y0 = arrival_s
        idx_last = self._n + count - 1  # the arrival time belongs to the newest sample
        y = arrival_s - self._y0

        # Track this block's fastest delivery (residual vs. the nominal grid).
        r = y - idx_last * self._nominal
        bno = idx_last // self._block
        if self._cur is None or self._cur[0] != bno:
            if self._cur is not None:
                self._minima.append((self._cur[1], self._cur[2]))
            self._cur = (bno, idx_last, r)
        elif r < self._cur[2]:
            self._cur = (bno, idx_last, r)

        self._hist.append((idx_last, y))
        period = self.period_s
        anchor = min(a - i * period for i, a in self._hist)

        out: list[float] = []
        for j in range(count):
            t = anchor + (self._n + j) * period
            if self._last is not None:
                t = max(t, self._last + _SLEW * period)
            self._last = t
            out.append(self._y0 + t)
        self._n += count
        return out

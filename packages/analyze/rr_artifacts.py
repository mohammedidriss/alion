"""RR-interval artifact detection after Lipponen & Tarvainen (2019), the method
behind Kubios' automatic correction (ADR-040).

Two adaptive thresholds, each 5.2 × the quartile deviation over the surrounding
91 beats: one for successive differences (dRR), one for each interval's distance
from the median of its 11 neighbours (mRR, shortening counted double). Every
interval is then classed by the shape of the dRR series around it:

- ectopic: a jump one way followed at once by one the other way;
- missed: one interval about twice the local median (two beats as one);
- extra: two short intervals that add up to about the local median;
- long or short: an outlier that fits neither pattern.

All four are artifacts. Alion deletes them rather than interpolating (RMSSD is
never computed across a removed beat), so only detection is implemented here.

One departure from the paper: both thresholds have a floor (`MIN_THRESHOLD_MS`).
With near-constant variability the quartile deviation tends to zero and every
ordinary beat would cross it; the floor keeps those in, and real artifacts —
hundreds of milliseconds off — are well above it.

Lipponen JA, Tarvainen MP. A robust algorithm for heart rate variability time
series artefact correction using novel beat classification. J Med Eng Technol
2019;43(3):173–181.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

ALPHA = 5.2  # × quartile deviation
WINDOW = 91  # beats for the thresholds
MEDIAN_ORDER = 11  # beats for the local median
C1, C2 = 0.13, 0.17  # ectopic decision boundary
MIN_THRESHOLD_MS = 30.0


def _threshold(x: np.ndarray) -> np.ndarray:
    """ALPHA × quartile deviation of |x| over a centred window, floored."""
    a = np.abs(x)
    half = WINDOW // 2
    out = np.empty(a.size)
    for i in range(a.size):
        w = a[max(0, i - half) : i + half + 1]
        q1, q3 = np.percentile(w, [25, 75])
        out[i] = ALPHA * (q3 - q1) / 2
    return np.maximum(out, MIN_THRESHOLD_MS)


def _local_median(rr: np.ndarray) -> np.ndarray:
    half = MEDIAN_ORDER // 2
    return np.array([np.median(rr[max(0, i - half) : i + half + 1]) for i in range(rr.size)])


def classify(rrs: Sequence[float]) -> list[str | None]:
    """For each interval: "ectopic", "missed", "extra", "longshort" or None."""
    rr = np.asarray(rrs, dtype=float)
    n = rr.size
    labels: list[str | None] = [None] * n
    if n < 3:
        return labels
    med = _local_median(rr)
    drr = np.diff(rr, prepend=rr[0])
    drr[0] = rr[0] - med[0]  # the first interval against its neighbourhood
    th1 = _threshold(drr)
    d = drr / th1
    mrr = rr - med
    mrr = np.where(mrr < 0, 2 * mrr, mrr)
    th2 = _threshold(mrr)
    m = mrr / th2

    p = np.pad(d, 2, mode="reflect")  # p[i + 2] == d[i]
    s12 = np.zeros(n)
    s22 = np.zeros(n)
    for i in range(n):
        prev_, next1, next2 = p[i + 1], p[i + 3], p[i + 4]
        if d[i] > 0:
            s12[i] = max(prev_, next1)
        elif d[i] < 0:
            s12[i] = min(prev_, next1)
        s22[i] = min(next1, next2) if d[i] >= 0 else max(next1, next2)

    def nxt(i: int) -> float:
        return float(rr[i + 1]) if i + 1 < n else float(med[i])

    i = 0
    while i < n:
        if abs(d[i]) <= 1:
            i += 1
            continue
        if (d[i] > 1 and s12[i] < -C1 * d[i] - C2) or (d[i] < -1 and s12[i] > -C1 * d[i] + C2):
            labels[i] = "ectopic"
            i += 1
            continue
        candidates = [i]
        if i + 2 < n and abs(d[i + 1]) < abs(d[i + 2]):
            candidates.append(i + 1)
        step = 1
        for j in candidates:
            long_ = d[j] > 1 and s22[j] < -1
            short = d[j] < -1 and s22[j] > 1
            far = abs(m[j]) > 3
            if not (long_ or short or far):
                continue
            if short and abs(rr[j] + nxt(j) - med[j]) < th2[j]:
                # Two short intervals around one extra beat: both go, as a pair.
                labels[j] = "extra"
                if j + 1 < n:
                    labels[j + 1] = "extra"
                step = j + 2 - i
                break
            labels[j] = "missed" if long_ and abs(rr[j] / 2 - med[j]) < th2[j] else "longshort"
        i += step
    return labels

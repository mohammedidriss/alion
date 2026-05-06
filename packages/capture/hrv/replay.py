"""CSV replay source for HRV streams.

Reads a CSV file of RR intervals (the format Polar H10 produces over
time) and yields `HRSample` events with proper timestamps. Lets us
develop, test, and run the entire HRV pipeline end-to-end without
needing a chest strap.

Accepted CSV shapes:
1. Single column `rr_ms` — t_ms is accumulated from the start of the
   stream (each beat advances by its own RR interval).
2. Two columns `t_ms,rr_ms` — t_ms is taken from the file directly.

Headers are required. Comment lines (starting with `#`) and blank lines
are skipped.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

from contracts import HRSample


def parse_rr_csv(path: str | Path) -> list[tuple[float, float]]:
    """Parse a CSV into a list of (t_ms, rr_ms) tuples — pure function, easy to test."""
    p = Path(path)
    rows: list[tuple[float, float]] = []
    with p.open() as f:
        reader = csv.DictReader(_strip_comments(f))
        if reader.fieldnames is None:
            return []
        cols = {c.strip().lower(): c for c in reader.fieldnames}
        if "rr_ms" not in cols:
            raise ValueError(f"CSV {p} must have an 'rr_ms' column (got {list(cols.keys())})")
        rr_col = cols["rr_ms"]
        t_col = cols.get("t_ms")
        running_t = 0.0
        for row in reader:
            rr_str = (row.get(rr_col) or "").strip()
            if not rr_str:
                continue
            try:
                rr = float(rr_str)
            except ValueError:
                continue
            if rr <= 0:
                continue
            if t_col is not None and (row.get(t_col) or "").strip():
                t = float(row[t_col])
            else:
                running_t += rr
                t = running_t
            rows.append((t, rr))
    return rows


def _strip_comments(lines: Iterator[str]) -> Iterator[str]:
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        yield ln


class CsvReplaySource:
    """Iterable that yields HRSamples from a CSV file at the session's pace.

    By default emits all samples back-to-back (offline / fast mode). Pass
    `realtime=True` to sleep between samples so the consumer sees them at
    roughly the rate they would arrive over BLE — useful for SSE testing.
    """

    def __init__(
        self,
        session_id: UUID,
        path: str | Path,
        *,
        realtime: bool = False,
    ) -> None:
        self.session_id = session_id
        self.path = Path(path)
        self.realtime = realtime

    def __iter__(self) -> Iterator[HRSample]:
        import time as _time

        rows = parse_rr_csv(self.path)
        last_t = 0.0
        for t_ms, rr_ms in rows:
            if self.realtime:
                gap_s = max(0.0, (t_ms - last_t) / 1000.0)
                if gap_s > 0:
                    _time.sleep(gap_s)
            yield HRSample(
                session_id=self.session_id,
                t_ms=t_ms,
                rr_ms=rr_ms,
                hr_bpm=60_000.0 / rr_ms,
            )
            last_t = t_ms

"""CSV replay source for the instrumented-mouthguard head-impact stream.

Mirrors `capture/hrv/replay.py`: reads a CSV of head-impact events and yields
`HeadImpactEvent`s so the whole mouthguard pipeline can be built, tested, and
demoed before the hardware is in hand (ADR 007; ADR 002 — synthetic data only
until Phase 8).

Accepted CSV shape (header required; `#` comment lines and blanks skipped):

    t_ms,peak_linear_accel_g,peak_rotational_vel_rad_s,peak_rotational_accel_rad_s2,location,confidence,device_id

Required columns: `t_ms`, `peak_linear_accel_g`, `peak_rotational_vel_rad_s`,
`location`. Optional: `peak_rotational_accel_rad_s2`, `confidence` (default
1.0), `device_id`. `t_ms` is already an offset from the session's `T_0`
(SessionClock), so replayed events need no clock conversion.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import get_args
from uuid import UUID

from contracts import HeadImpactEvent, ImpactLocation

_VALID_LOCATIONS: frozenset[str] = frozenset(get_args(ImpactLocation))


@dataclass(frozen=True)
class ImpactReading:
    """The physical quantities of one head impact — no session/time context.

    The clock-independent payload a device (or replay row) reports; the source
    pairs it with a `session_id` and a `t_ms` offset to build a
    `HeadImpactEvent`.
    """

    peak_linear_accel_g: float
    peak_rotational_vel_rad_s: float
    location: ImpactLocation
    peak_rotational_accel_rad_s2: float | None = None
    confidence: float = 1.0
    device_id: str | None = None


def parse_impacts_csv(path: str | Path) -> list[tuple[float, ImpactReading]]:
    """Parse a head-impact CSV file into (t_ms, ImpactReading) tuples."""
    with Path(path).open() as f:
        return _parse_impacts_lines(f)


def parse_impacts_text(text: str) -> list[tuple[float, ImpactReading]]:
    """Parse head-impact CSV *text* (e.g. an uploaded body) — same rules as the file parser."""
    import io

    return _parse_impacts_lines(io.StringIO(text))


def _parse_impacts_lines(lines: Iterator[str]) -> list[tuple[float, ImpactReading]]:
    """Core parser over an iterable of CSV lines — pure.

    Rows with a missing/invalid required field or an unknown `location` are
    skipped (same lenient policy as the HRV replay parser).
    """
    rows: list[tuple[float, ImpactReading]] = []
    reader = csv.DictReader(_strip_comments(lines))
    if reader.fieldnames is None:
        return []
    cols = {c.strip().lower(): c for c in reader.fieldnames}
    required = ("t_ms", "peak_linear_accel_g", "peak_rotational_vel_rad_s", "location")
    if any(r not in cols for r in required):
        missing = [r for r in required if r not in cols]
        raise ValueError(f"CSV missing required column(s): {missing}")

    for row in reader:
        parsed = _parse_row(row, cols)
        if parsed is not None:
            rows.append(parsed)
    return rows


def _parse_row(row: dict[str, str], cols: dict[str, str]) -> tuple[float, ImpactReading] | None:
    def _get(key: str) -> str:
        return (row.get(cols[key]) or "").strip() if key in cols else ""

    location = _get("location").lower()
    if location not in _VALID_LOCATIONS:
        return None
    try:
        t_ms = float(_get("t_ms"))
        pla = float(_get("peak_linear_accel_g"))
        prv = float(_get("peak_rotational_vel_rad_s"))
    except ValueError:
        return None
    if t_ms < 0 or pla < 0 or prv < 0:
        return None

    pra_str = _get("peak_rotational_accel_rad_s2")
    try:
        pra = float(pra_str) if pra_str else None
    except ValueError:
        pra = None

    conf_str = _get("confidence")
    try:
        confidence = float(conf_str) if conf_str else 1.0
    except ValueError:
        confidence = 1.0
    confidence = min(1.0, max(0.0, confidence))

    device_id = _get("device_id") or None

    reading = ImpactReading(
        peak_linear_accel_g=pla,
        peak_rotational_vel_rad_s=prv,
        location=location,  # type: ignore[arg-type]  # checked against _VALID_LOCATIONS
        peak_rotational_accel_rad_s2=pra,
        confidence=confidence,
        device_id=device_id,
    )
    return t_ms, reading


def _strip_comments(lines: Iterator[str]) -> Iterator[str]:
    for ln in lines:
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        yield ln


class CsvImpactReplaySource:
    """Iterable that yields `HeadImpactEvent`s from a CSV at the session's pace.

    By default emits all events back-to-back (offline / fast mode). Pass
    `realtime=True` to sleep between events so a consumer sees them roughly
    when they would arrive over BLE.
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

    def __iter__(self) -> Iterator[HeadImpactEvent]:
        import time as _time

        rows = parse_impacts_csv(self.path)
        last_t = 0.0
        for t_ms, reading in rows:
            if self.realtime:
                gap_s = max(0.0, (t_ms - last_t) / 1000.0)
                if gap_s > 0:
                    _time.sleep(gap_s)
            yield HeadImpactEvent(
                session_id=self.session_id,
                t_ms=t_ms,
                peak_linear_accel_g=reading.peak_linear_accel_g,
                peak_rotational_vel_rad_s=reading.peak_rotational_vel_rad_s,
                peak_rotational_accel_rad_s2=reading.peak_rotational_accel_rad_s2,
                location=reading.location,
                device_id=reading.device_id,
                confidence=reading.confidence,
            )
            last_t = t_ms

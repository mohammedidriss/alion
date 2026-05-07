"""Time helpers — primitives for cross-modality stream alignment.

`SessionClock` is the per-session T_0 reference. It anchors at a single
wall-clock instant when the session starts capturing, and produces
millisecond offsets that are directly comparable across the CV pipeline,
the HRV stream, and (eventually) IMU. This is the precondition for any
"X at Y" question — "heart rate at impact", "punch velocity at 2.4s".

In-process precision uses `time.monotonic_ns` (immune to NTP slew during a
session). External timestamps that arrive as wall-clock datetimes
(e.g. Polar H10 BLE samples re-stamped by the OS) are converted via the
wall-clock anchor.

Per ADR (Gemini critical refinement #1): all sensor packets crossing from
an Adapter (capture/*) into the Domain (analyze) must be tagged with
offsets relative to T_0 — never raw arrival times.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def ms_offset(t0: datetime, t1: datetime) -> float:
    """Return (t1 - t0) in milliseconds. Negative if t1 precedes t0."""
    return (t1 - t0).total_seconds() * 1000.0


@dataclass(frozen=True)
class SessionClock:
    """Per-session T_0 reference. Construct via `SessionClock.start()`.

    Two anchors are stored so the clock can serve in-process events
    (precise, NTP-immune) and externally-timestamped events (wall-clock
    arithmetic):

    - `wall_t0`: UTC datetime when capture started — the "session start"
      that ends up in `Session.started_at`.
    - `monotonic_ns_t0`: process-monotonic counter at the same instant.
      Use for in-process events whose source is `time.monotonic_ns()`.
    """

    wall_t0: datetime
    monotonic_ns_t0: int

    @classmethod
    def start(cls, wall_t0: datetime | None = None) -> SessionClock:
        """Anchor a new clock at "now". Pass an explicit `wall_t0` to align
        with a Session row that was just created (so `Session.started_at`
        and the clock's wall anchor match exactly)."""
        return cls(
            wall_t0=wall_t0 or datetime.now(UTC),
            monotonic_ns_t0=time.monotonic_ns(),
        )

    # ---- in-process events (monotonic, precise) ----

    def now_offset_ms(self) -> float:
        """Current offset from T_0, ms. Use for events generated in-process."""
        return (time.monotonic_ns() - self.monotonic_ns_t0) / 1_000_000.0

    def offset_from_monotonic_ns(self, monotonic_ns: int) -> float:
        """Convert any in-process `time.monotonic_ns()` reading to an offset."""
        return (monotonic_ns - self.monotonic_ns_t0) / 1_000_000.0

    # ---- externally-timestamped events (wall-clock) ----

    def offset_from_wall(self, dt: datetime) -> float:
        """Convert an external wall-clock instant to ms offset from T_0.

        Use for samples that arrive with their own absolute timestamp
        (e.g. Polar H10 BLE packets re-stamped by the OS). Subject to
        wall-clock skew — fine for HR (1 Hz) and rough sync, but for
        sub-50 ms alignment prefer the monotonic path.
        """
        return ms_offset(self.wall_t0, dt)

    # ---- inversion ----

    def wall_for_offset(self, offset_ms: float) -> datetime:
        """Reconstruct the wall-clock instant for a given offset.

        Used when displaying CV punch events (which carry only `t_ms`) on
        a clock UI, or when correlating CV events with external systems
        that index by wall-clock time.
        """
        from datetime import timedelta

        return self.wall_t0 + timedelta(milliseconds=offset_ms)

"""Time helpers — used heavily for clap-sync offset math in Phase 2."""

from __future__ import annotations

from datetime import UTC, datetime


def now_utc() -> datetime:
    return datetime.now(UTC)


def ms_offset(t0: datetime, t1: datetime) -> float:
    """Return (t1 - t0) in milliseconds. Negative if t1 precedes t0."""
    return (t1 - t0).total_seconds() * 1000.0

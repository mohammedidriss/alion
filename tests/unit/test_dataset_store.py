"""Take folder writers (ADR-013)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from api.services import dataset_store
from store import HRSampleRow


def _row(t: float, bpm: float) -> HRSampleRow:
    return HRSampleRow(session_id=uuid4(), t_ms=t, rr_ms=60_000 / bpm, hr_bpm=bpm)


def test_heart_rate_is_stored_from_the_cameras_start_on_the_take_timeline(tmp_path: Path) -> None:
    """The strap connects early; beats before t = 0 (or before any start) are dropped
    and the rest land on the take's timeline."""
    t0: list[float | None] = [None]
    write = dataset_store.hr_writer(tmp_path, lambda: t0[0])
    write([_row(1_000_000.0, 80)])  # cameras not started yet → nothing
    assert not (tmp_path / "hr.csv").exists()
    t0[0] = 1_000_500.0
    write([_row(1_000_400.0, 81), _row(1_001_250.0, 82)])
    lines = (tmp_path / "hr.csv").read_text().splitlines()
    assert lines == ["t_ms,rr_ms,hr_bpm", "750.0,731.7,82.0"]

"""CSV replay source — parses RR-interval CSVs and emits HRSample events."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from capture.hrv import CsvReplaySource, parse_rr_csv


def _write_csv(path: Path, header: str, rows: list[str]) -> None:
    path.write_text(header + "\n" + "\n".join(rows) + "\n")


def test_parse_single_column_accumulates_t_ms(tmp_path: Path) -> None:
    csv = tmp_path / "rr.csv"
    _write_csv(csv, "rr_ms", ["800", "820", "810", "790"])
    rows = parse_rr_csv(csv)
    assert [r[0] for r in rows] == [800.0, 1620.0, 2430.0, 3220.0]
    assert [r[1] for r in rows] == [800.0, 820.0, 810.0, 790.0]


def test_parse_two_column_uses_t_ms_directly(tmp_path: Path) -> None:
    csv = tmp_path / "rr.csv"
    _write_csv(csv, "t_ms,rr_ms", ["0,800", "800,820", "1620,810"])
    rows = parse_rr_csv(csv)
    assert rows == [(0.0, 800.0), (800.0, 820.0), (1620.0, 810.0)]


def test_skips_blank_lines_and_comments(tmp_path: Path) -> None:
    csv = tmp_path / "rr.csv"
    csv.write_text("# Polar export 2026-05-06\nrr_ms\n800\n\n820\n# pause\n810\n")
    rows = parse_rr_csv(csv)
    assert [r[1] for r in rows] == [800.0, 820.0, 810.0]


def test_rejects_csv_without_rr_column(tmp_path: Path) -> None:
    csv = tmp_path / "rr.csv"
    _write_csv(csv, "timestamp,heart_rate", ["0,72", "1,73"])
    with pytest.raises(ValueError, match="rr_ms"):
        parse_rr_csv(csv)


def test_replay_source_emits_hr_samples(tmp_path: Path) -> None:
    sid = uuid4()
    csv = tmp_path / "rr.csv"
    _write_csv(csv, "rr_ms", ["800", "750", "820"])
    samples = list(CsvReplaySource(session_id=sid, path=csv))
    assert len(samples) == 3
    assert samples[0].session_id == sid
    assert samples[0].rr_ms == 800
    assert samples[0].hr_bpm == pytest.approx(75.0)  # 60000 / 800
    assert samples[1].hr_bpm == pytest.approx(80.0)  # 60000 / 750
    # t_ms accumulates from running total of RRs
    assert samples[2].t_ms == 800 + 750 + 820


def test_replay_source_skips_zero_or_negative_rr(tmp_path: Path) -> None:
    sid = uuid4()
    csv = tmp_path / "rr.csv"
    _write_csv(csv, "rr_ms", ["800", "0", "-5", "820"])
    samples = list(CsvReplaySource(session_id=sid, path=csv))
    assert [s.rr_ms for s in samples] == [800.0, 820.0]

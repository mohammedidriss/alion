"""Mouthguard head-impact replay + event assembly (ADR 007)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from capture.mouthguard import (
    CsvImpactReplaySource,
    ImpactReading,
    impact_event_from_reading,
    parse_impacts_csv,
)
from common import SessionClock, now_utc

_CSV = """\
# head-impact replay — one row per impact
t_ms,peak_linear_accel_g,peak_rotational_vel_rad_s,peak_rotational_accel_rad_s2,location,confidence,device_id
1200,42.5,18.3,3400,chin,0.92,MG-001
2500,31.0,12.1,,front,,MG-001
4100,55.8,24.6,5200,left,0.99,MG-001
"""


def _write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "impacts.csv"
    p.write_text(text)
    return p


def test_parse_impacts_csv_basic(tmp_path: Path) -> None:
    rows = parse_impacts_csv(_write(tmp_path, _CSV))
    assert len(rows) == 3
    t0, r0 = rows[0]
    assert t0 == 1200.0
    assert r0.peak_linear_accel_g == 42.5
    assert r0.peak_rotational_vel_rad_s == 18.3
    assert r0.peak_rotational_accel_rad_s2 == 3400.0
    assert r0.location == "chin"
    assert r0.confidence == 0.92
    assert r0.device_id == "MG-001"


def test_optional_fields_default(tmp_path: Path) -> None:
    rows = parse_impacts_csv(_write(tmp_path, _CSV))
    _, r1 = rows[1]  # row with empty pra + confidence
    assert r1.peak_rotational_accel_rad_s2 is None
    assert r1.confidence == 1.0  # default when blank


def test_unknown_location_row_skipped(tmp_path: Path) -> None:
    bad = (
        "t_ms,peak_linear_accel_g,peak_rotational_vel_rad_s,location\n"
        "100,10,5,elbow\n"  # not a head location
        "200,12,6,front\n"
    )
    rows = parse_impacts_csv(_write(tmp_path, bad))
    assert len(rows) == 1
    assert rows[0][1].location == "front"


def test_malformed_numeric_row_skipped(tmp_path: Path) -> None:
    bad = (
        "t_ms,peak_linear_accel_g,peak_rotational_vel_rad_s,location\n"
        "abc,10,5,front\n"  # bad t_ms
        "300,notanumber,5,front\n"  # bad accel
        "400,15,7,back\n"
    )
    rows = parse_impacts_csv(_write(tmp_path, bad))
    assert len(rows) == 1
    assert rows[0][0] == 400.0


def test_missing_required_column_raises(tmp_path: Path) -> None:
    bad = "t_ms,peak_linear_accel_g,location\n100,10,front\n"  # no rotational vel
    with pytest.raises(ValueError, match="missing required column"):
        parse_impacts_csv(_write(tmp_path, bad))


def test_replay_source_yields_head_impact_events(tmp_path: Path) -> None:
    sid = uuid4()
    events = list(CsvImpactReplaySource(sid, _write(tmp_path, _CSV)))
    assert len(events) == 3
    assert all(e.session_id == sid for e in events)
    # t_ms preserved from the file (already a T_0 offset), ordered.
    assert [e.t_ms for e in events] == [1200.0, 2500.0, 4100.0]
    assert events[0].location == "chin"
    assert events[2].peak_linear_accel_g == 55.8


def test_impact_event_from_reading_maps_fields_and_t0() -> None:
    """The assembler tags an ImpactReading against a SessionClock T_0 offset."""
    sid = uuid4()
    clock = SessionClock.start()
    reading = ImpactReading(
        peak_linear_accel_g=48.0,
        peak_rotational_vel_rad_s=20.0,
        location="top",
        peak_rotational_accel_rad_s2=4100.0,
        confidence=0.8,
        device_id="MG-9",
    )
    t_ms = clock.offset_from_wall(now_utc())
    event = impact_event_from_reading(sid, reading, t_ms)

    assert event.session_id == sid
    assert event.t_ms == t_ms
    assert event.t_ms >= 0.0  # after T_0
    assert event.peak_linear_accel_g == 48.0
    assert event.peak_rotational_vel_rad_s == 20.0
    assert event.peak_rotational_accel_rad_s2 == 4100.0
    assert event.location == "top"
    assert event.confidence == 0.8
    assert event.device_id == "MG-9"

"""Performance with the body sensors on the Observations tab (ADR-027): the trend
and the AI observations read each session's settled punches — the wrist ↔ camera
cross-check for a camera session — and what the strap and the wrists recorded."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from store import (
    DetectionSourceEnum,
    HandEnum,
    HRSampleRow,
    IMUSampleRow,
    PunchEventRow,
    SessionStatus,
)
from store import Session as SessionRow


@pytest.fixture
def pose_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from api.services import session_analysis

    monkeypatch.setattr(session_analysis, "POSE_DIR", tmp_path)
    return tmp_path


def _completed(client: TestClient, db: Session, fid: str, days_ago: int, minutes: float) -> UUID:
    sid = UUID(
        client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    )
    row = db.get(SessionRow, sid)
    assert row is not None
    row.status = SessionStatus.COMPLETED
    row.started_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days_ago)
    row.duration_ms = minutes * 60_000
    db.add(row)
    db.commit()
    return sid


def _cross_check(pose_dir: Path, sid: UUID) -> None:
    from api.services import cross_check

    punches = [
        # counted: confirmed by both, wrist-only, and a camera detection not counted
        {
            "t_ms": 1000,
            "hand": "left",
            "source": "both",
            "counted": True,
            "peak_g": 8.0,
            "speed_ms": 5.0,
        },
        {
            "t_ms": 2000,
            "hand": "right",
            "source": "both",
            "counted": True,
            "peak_g": 10.0,
            "speed_ms": 6.0,
        },
        {
            "t_ms": 3000,
            "hand": "left",
            "source": "wrist",
            "counted": True,
            "peak_g": 6.0,
            "speed_ms": None,
        },
        {
            "t_ms": 4000,
            "hand": "right",
            "source": "camera",
            "counted": False,
            "peak_g": None,
            "speed_ms": 9.0,
        },
    ]
    (pose_dir / f"{sid}.crosscheck.json").write_text(
        json.dumps({"version": cross_check.VERSION, "punches": punches, "totals": {"counted": 3}})
    )


def test_a_camera_session_shows_its_cross_checked_punches_heart_rate_and_wrist_force(
    authed_client: TestClient, session: Session, pose_dir: Path
) -> None:
    fid = authed_client.post("/fighters", json={"name": "Obs"}).json()["id"]
    cam = _completed(authed_client, session, fid, days_ago=2, minutes=1.0)
    _cross_check(pose_dir, cam)
    for i, rr in enumerate([600.0, 500.0, 600.0]):
        session.add(HRSampleRow(session_id=cam, t_ms=i * 600.0, rr_ms=rr, hr_bpm=60000 / rr))
    session.add(IMUSampleRow(session_id=cam, t_ms=0, ax_g=12.0, ay_g=0, az_g=0, hand=HandEnum.LEFT))
    session.add(
        IMUSampleRow(session_id=cam, t_ms=10, ax_g=1.0, ay_g=0, az_g=0, hand=HandEnum.RIGHT)
    )

    old = _completed(authed_client, session, fid, days_ago=9, minutes=2.0)  # punch table only
    for i in range(4):
        session.add(
            PunchEventRow(
                session_id=old,
                t_ms=i * 1000.0,
                hand=HandEnum.LEFT,
                velocity_ms=4.0,
                detected_by=DetectionSourceEnum.HEURISTIC,
                confidence=0.9,
            )
        )
    empty = _completed(authed_client, session, fid, days_ago=5, minutes=0.0)  # never timed
    session.commit()

    items = {
        i["session_id"]: i
        for i in authed_client.get(f"/fighters/{fid}/performance-trend").json()["items"]
    }
    c = items[str(cam)]
    # Counted punches only (3), not the camera detection the wrists didn't confirm.
    assert c["punch_source"] == "cross_check" and c["punch_count"] == 3 and c["ppm"] == 3.0
    assert c["avg_punch_g"] == 8.0 and c["peak_wrist_g"] == 12.0
    assert c["mean_hr_bpm"] is not None and c["max_hr_bpm"] == 120.0 and c["rmssd_ms"] == 100.0

    o = items[str(old)]
    assert o["punch_source"] == "camera" and o["punch_count"] == 4 and o["ppm"] == 2.0
    assert o["mean_hr_bpm"] is None and o["avg_punch_g"] is None

    e = items[str(empty)]
    assert e["punch_source"] == "none" and e["ppm"] == 0.0  # no divide-by-zero rate


def test_the_ai_observations_see_the_combined_numbers(
    authed_client: TestClient, session: Session, pose_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coach import llm_client

    sent: dict[str, Any] = {}

    async def fake_generate(system_prompt: str, user_content: str) -> str:
        sent.update(json.loads(user_content))
        return json.dumps(
            {
                "observations": ["Volume held up."],
                "strengths": [],
                "weaknesses": [],
                "training_plan": ["Keep the rounds the same."],
                "summary": "Steady.",
            }
        )

    monkeypatch.setattr(llm_client, "generate_raw", fake_generate)
    fid = authed_client.post("/fighters", json={"name": "Obs2"}).json()["id"]
    a = _completed(authed_client, session, fid, days_ago=3, minutes=1.0)
    _cross_check(pose_dir, a)
    session.add(HRSampleRow(session_id=a, t_ms=0, rr_ms=600.0, hr_bpm=100.0))
    session.add(HRSampleRow(session_id=a, t_ms=600, rr_ms=600.0, hr_bpm=100.0))
    _completed(authed_client, session, fid, days_ago=1, minutes=1.0)  # nothing recorded
    session.commit()

    r = authed_client.post(f"/fighters/{fid}/observations/generate")
    assert r.status_code == 200, r.text
    first, second = sent["sessions"]
    assert first["punch_count"] == 3 and first["avg_punch_force_g"] == 8.0
    assert first["session_mean_hr_bpm"] == 100.0
    # What wasn't recorded isn't sent at all — no nulls for the model to misread.
    assert "session_mean_hr_bpm" not in second and "avg_punch_force_g" not in second


def test_a_session_with_wrists_but_no_camera_pose_counts_from_the_wrists(
    authed_client: TestClient, session: Session, pose_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import sensor_summary

    monkeypatch.setattr(
        sensor_summary,
        "wrist_punches",
        lambda samples: [(100.0, "left", 6.0), (900.0, "right", 8.0)] if samples else [],
    )
    fid = authed_client.post("/fighters", json={"name": "Wrists"}).json()["id"]
    sid = _completed(authed_client, session, fid, days_ago=1, minutes=0.5)
    session.add(IMUSampleRow(session_id=sid, t_ms=0, ax_g=1.0, ay_g=0, az_g=0, hand=HandEnum.LEFT))
    session.commit()
    item = authed_client.get(f"/fighters/{fid}/performance-trend").json()["items"][0]
    assert item["punch_source"] == "wrist" and item["punch_count"] == 2 and item["ppm"] == 4.0
    assert item["avg_punch_g"] == 7.0
    assert item["peak_velocity_ms"] is None and item["score"] is None  # no speed was measured

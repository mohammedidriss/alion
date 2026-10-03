"""Live reader endpoint — latest beats, HR zone, and the wrist status in one poll."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session

from api.routes.live import hr_zone, max_hr_for
from api.services.imu_runner import UnitState
from store import HRSampleRow


def test_max_hr_uses_age_and_needs_a_birthday() -> None:
    assert max_hr_for(None) is None
    # 40 on the day: 208 − 0.7·40 = 180
    assert max_hr_for(date(1986, 10, 3), today=date(2026, 10, 3)) == 180
    # one day before the birthday they're still 39
    assert max_hr_for(date(1986, 10, 4), today=date(2026, 10, 3)) == round(208 - 0.7 * 39)


def test_hr_zones_follow_percent_of_max() -> None:
    assert [hr_zone(b, 200) for b in (90, 100, 125, 145, 170, 185, 210)] == [0, 1, 2, 3, 4, 5, 5]
    assert hr_zone(159, 200) == 3 and hr_zone(160, 200) == 4
    assert [hr_zone(b, 200) for b in (120, 140, 180)] == [2, 3, 5]  # exact boundaries


def test_live_returns_the_latest_beats_oldest_first(
    authed_client: TestClient, session: Session
) -> None:
    fid = authed_client.post("/fighters", json={"name": "Mohamad", "dob": "1990-01-01"}).json()[
        "id"
    ]
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
        "id"
    ]
    for i in range(80):  # more than the 60 the reader gets
        session.add(HRSampleRow(session_id=UUID(sid), t_ms=i * 800.0, rr_ms=800.0, hr_bpm=100 + i))
    session.commit()

    body = authed_client.get(f"/v2/sessions/{sid}/live").json()
    heart = body["heart"]
    assert heart["streaming"] is False
    assert heart["bpm_trace"] == [float(100 + i) for i in range(20, 80)]  # newest 60, in order
    assert heart["bpm"] == 179.0
    assert heart["max_hr"] is not None and heart["zone"] in range(6)
    assert body["imu"]["running"] is False


def test_live_404s_unknown_session(authed_client: TestClient) -> None:
    r = authed_client.get("/v2/sessions/00000000-0000-0000-0000-000000000000/live")
    assert r.status_code == 404


def test_wrist_trace_keeps_each_buckets_peak() -> None:
    u = UnitState()
    for t, g in [(0, 1.0), (10, 6.0), (20, 1.0), (60, 1.1), (110, 0.9)]:
        u.observe(t, g)
    assert list(u.trace) == [6.0, 1.1, 0.9]  # 0–49 ms peak, 50–99, 100–149

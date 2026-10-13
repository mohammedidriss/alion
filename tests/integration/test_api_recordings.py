"""Every session's heart-rate and wrist recordings, for the HRV and IMU tabs."""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session

from store import HandEnum, HRSampleRow, IMUSampleRow, SessionStatus
from store import Session as SessionRow


def _session(client: TestClient, fid: str) -> str:
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def _mark_recorded(db: Session, sid: str) -> None:
    row = db.get(SessionRow, UUID(sid))
    assert row is not None
    row.status = SessionStatus.COMPLETED
    row.video_path = "data/raw/uploaded/x.webm"  # the cameras recorded it
    db.add(row)
    db.commit()


def test_every_recorded_session_is_listed_with_what_its_sensors_stored(
    authed_client: TestClient, session: Session
) -> None:
    fid = authed_client.post("/fighters", json={"name": "Rec"}).json()["id"]
    with_both, cameras_only, never_recorded = (_session(authed_client, fid) for _ in range(3))
    _mark_recorded(session, with_both)
    _mark_recorded(session, cameras_only)

    sid = UUID(with_both)
    for i, rr in enumerate([600.0, 620.0, 610.0, 630.0]):  # 4 beats over ~2.5 s
        session.add(HRSampleRow(session_id=sid, t_ms=i * 610.0, rr_ms=rr, hr_bpm=60000 / rr))
    for i in range(101):  # 1 s of the left wrist at 100 Hz, one 3 g spike
        g = 3.0 if i == 50 else 1.0
        session.add(
            IMUSampleRow(
                session_id=sid, t_ms=i * 10.0, ax_g=g, ay_g=0.0, az_g=0.0, hand=HandEnum.LEFT
            )
        )
    session.commit()

    r = authed_client.get(f"/v2/fighters/{fid}/recordings")
    assert r.status_code == 200
    rows = {x["session_id"]: x for x in r.json()}
    assert set(rows) == {with_both, cameras_only}  # opened and left unrecorded: not listed

    heart = rows[with_both]["heart"]
    assert heart["beats"] == 4 and heart["max_hr_bpm"] == 100.0
    assert heart["rmssd_ms"] == 17.3  # successive differences 20, −10, 20: √300
    left = rows[with_both]["wrists"]["left"]
    assert left == {"samples": 101, "duration_s": 1.0, "hz": 100.0, "peak_g": 3.0}

    # A recorded session without sensor data is still listed — the gap is visible.
    assert rows[cameras_only]["heart"] is None and rows[cameras_only]["wrists"] == {}
    assert never_recorded not in rows


def test_unknown_fighter_is_404(authed_client: TestClient) -> None:
    r = authed_client.get("/v2/fighters/00000000-0000-0000-0000-000000000000/recordings")
    assert r.status_code == 404


def test_dropouts_do_not_swamp_the_heart_rate_variability(
    authed_client: TestClient, session: Session
) -> None:
    fid = authed_client.post("/fighters", json={"name": "Gap"}).json()["id"]
    sid = _session(authed_client, fid)
    _mark_recorded(session, sid)
    # Steady beats with one 4.6 s dropout in the middle.
    for i, rr in enumerate([600.0, 610.0, 4600.0, 600.0, 610.0]):
        session.add(HRSampleRow(session_id=UUID(sid), t_ms=i * 1000.0, rr_ms=rr, hr_bpm=60000 / rr))
    session.commit()
    heart = authed_client.get(f"/v2/fighters/{fid}/recordings").json()[0]["heart"]
    assert heart["beats"] == 5  # every stored beat is counted
    assert heart["rmssd_ms"] < 20  # but the dropout isn't a heartbeat

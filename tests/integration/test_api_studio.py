"""Capture survives API restarts, and phones link once (camera studio).

uvicorn --reload restarts the API on every code save; that used to wipe the
in-memory join tokens (phones got 403) and the running capture. A restart is
simulated here by clearing the coordinator's memory.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def capture_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.routes import capture_coord, studio
    from api.services import dataset_store

    monkeypatch.setattr(capture_coord, "_STATE_DIR", tmp_path / "capture")
    monkeypatch.setattr(capture_coord, "_VIDEO_DIR", tmp_path / "clips")
    monkeypatch.setattr(studio, "_STATE_DIR", tmp_path / "capture")
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", tmp_path / "datasets")
    yield tmp_path


def _restart_api() -> None:
    """What a uvicorn reload does to the in-memory capture state."""
    from api.routes import capture_coord, studio

    capture_coord._coords.clear()
    studio._active.clear()
    studio._phones.clear()


def _session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Mohamad"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def test_a_phones_join_token_and_the_recording_survive_a_restart(
    authed_client: TestClient, capture_dirs: Path
) -> None:
    sid = _session(authed_client)
    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    dev = authed_client.post(
        f"/sessions/{sid}/multicam/register", json={"token": token, "label": "samsung"}
    ).json()["device_id"]
    start_at = authed_client.post(f"/sessions/{sid}/multicam/start").json()["start_at_ms"]

    _restart_api()

    # the QR the phone scanned is still valid, and the recording carries on with t = 0
    st = authed_client.post(
        f"/sessions/{sid}/multicam/heartbeat",
        json={"token": token, "device_id": dev, "status": "recording", "label": "samsung"},
    )
    assert st.status_code == 200
    assert st.json()["command"] == "start" and st.json()["start_at_ms"] == start_at
    # the phone is back on the coach's roster from that heartbeat
    roster = authed_client.get(f"/sessions/{sid}/multicam/devices").json()
    assert [(d["device_id"], d["label"], d["status"]) for d in roster] == [
        (dev, "samsung", "recording")
    ]
    # a made-up token is still refused
    bad = authed_client.post(
        f"/sessions/{sid}/multicam/heartbeat", json={"token": "nope", "device_id": dev}
    )
    assert bad.status_code == 403


def test_linked_phones_follow_the_capture_the_coach_opens(
    authed_client: TestClient, capture_dirs: Path
) -> None:
    studio = authed_client.get("/v2/studio").json()
    assert studio["active"] is None and studio["phones"] == []
    link = studio["join_path"].split("studio=", 1)[1]

    # a linked phone with nothing open waits
    st = authed_client.get(f"/studio/state?token={link}&phone_id=p1&label=Samsung").json()
    assert st["active"] is None
    assert authed_client.get("/v2/studio").json()["phones"] == [
        {"phone_id": "p1", "label": "Samsung"}
    ]

    # the coach opens a session → the phone is told to join it, with a working token
    sid = _session(authed_client)
    authed_client.put("/v2/studio/active", json={"kind": "session", "id": sid})
    st = authed_client.get(f"/studio/state?token={link}&phone_id=p1&label=Samsung").json()
    assert st["active"]["kind"] == "session" and st["active"]["id"] == sid
    reg = authed_client.post(
        f"/sessions/{sid}/multicam/register", json={"token": st["active"]["join_token"]}
    )
    assert reg.status_code == 200

    # the active capture survives a restart too
    _restart_api()
    st = authed_client.get(f"/studio/state?token={link}").json()
    assert st["active"]["id"] == sid

    # a forged studio link is refused; an unknown capture can't be made active
    assert authed_client.get("/studio/state?token=abc.def").status_code == 403
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        authed_client.put("/v2/studio/active", json={"kind": "take", "id": missing}).status_code
        == 404
    )


def test_a_camera_renamed_on_the_phone_is_renamed_for_the_coach(
    authed_client: TestClient, capture_dirs: Path
) -> None:
    sid = _session(authed_client)
    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    dev = authed_client.post(
        f"/sessions/{sid}/multicam/register", json={"token": token, "label": "front"}
    ).json()["device_id"]
    authed_client.post(
        f"/sessions/{sid}/multicam/heartbeat",
        json={"token": token, "device_id": dev, "status": "ready", "label": "SM-S918B"},
    )
    roster = authed_client.get(f"/sessions/{sid}/multicam/devices").json()
    assert [d["label"] for d in roster] == ["SM-S918B"]


def test_deleting_a_session_removes_its_clips(
    authed_client: TestClient, capture_dirs: Path
) -> None:
    sid = _session(authed_client)
    clips = capture_dirs / "clips"
    clips.mkdir(parents=True)
    (clips / f"{sid}.a1b2c3d4.webm").write_bytes(b"clip")
    (clips / f"{sid}.a1b2c3d4.json").write_text('{"start_offset_ms": 12}')
    (clips / "someone-else.a1b2c3d4.webm").write_bytes(b"keep")
    assert authed_client.delete(f"/sessions/{sid}").status_code == 204
    assert sorted(p.name for p in clips.iterdir()) == ["someone-else.a1b2c3d4.webm"]

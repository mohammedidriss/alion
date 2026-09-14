"""Multi-device capture coordinator — device roster + synchronized start (ADR-010)."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

# Import the route so its schemas/state load with the app.
from api.routes import capture_coord as _cc  # noqa: F401


def _make_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Cam"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def test_join_register_roster_start_flow(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)

    # Coach fetches the join token + camera-page path for the QR.
    ji = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()
    token = ji["join_token"]
    assert token and f"/sessions/{sid}/camera" in ji["join_path"]
    assert ji.get("lan_ip")  # so the panel can build a phone-reachable URL

    # No devices yet → start refused, roster empty.
    assert authed_client.post(f"/sessions/{sid}/multicam/start").status_code == 409
    assert authed_client.get(f"/sessions/{sid}/multicam/devices").json() == []

    # A phone registers with the token.
    reg = authed_client.post(
        f"/sessions/{sid}/multicam/register",
        json={"token": token, "role": "camera", "label": "front"},
    )
    assert reg.status_code == 200
    dev_id = reg.json()["device_id"]

    # It shows on the coach's roster.
    roster = authed_client.get(f"/sessions/{sid}/multicam/devices").json()
    assert len(roster) == 1 and roster[0]["label"] == "front"

    # Coach starts → a start scheduled in the future; the phone polls and sees it.
    started = authed_client.post(f"/sessions/{sid}/multicam/start").json()
    assert started["command"] == "start" and started["devices"] == 1
    state = authed_client.get(f"/sessions/{sid}/multicam/state", params={"token": token}).json()
    assert state["command"] == "start"
    assert state["start_at_ms"] > state["server_now_ms"]  # scheduled ahead of now

    # Heartbeat keeps it alive and flips its status.
    hb = authed_client.post(
        f"/sessions/{sid}/multicam/heartbeat",
        json={"token": token, "device_id": dev_id, "status": "recording"},
    ).json()
    assert hb["command"] == "start"
    assert authed_client.get(f"/sessions/{sid}/multicam/devices").json()[0]["status"] == "recording"

    # Stop clears the command.
    authed_client.post(f"/sessions/{sid}/multicam/stop")
    got = authed_client.get(f"/sessions/{sid}/multicam/state", params={"token": token}).json()
    assert got["command"] == "stop" and got["start_at_ms"] is None


def test_pause_resume_flow(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    dev_id = authed_client.post(
        f"/sessions/{sid}/multicam/register",
        json={"token": token, "role": "camera", "label": "front"},
    ).json()["device_id"]
    authed_client.post(f"/sessions/{sid}/multicam/start")

    # Pause holds recording: paused=True, but the command stays "start" so the clip
    # is kept open (only Stop finalizes).
    p = authed_client.post(f"/sessions/{sid}/multicam/pause").json()
    assert p["paused"] is True and p["command"] == "start"
    st = authed_client.get(f"/sessions/{sid}/multicam/state", params={"token": token}).json()
    assert st["paused"] is True and st["command"] == "start"

    # Heartbeat carries the paused flag so the phone can hold its recorder.
    hb = authed_client.post(
        f"/sessions/{sid}/multicam/heartbeat",
        json={"token": token, "device_id": dev_id, "status": "paused"},
    ).json()
    assert hb["paused"] is True

    # Resume clears it; the same recording continues.
    r = authed_client.post(f"/sessions/{sid}/multicam/resume").json()
    assert r["paused"] is False and r["command"] == "start"

    # Stop ends the match and clears paused.
    s = authed_client.post(f"/sessions/{sid}/multicam/stop").json()
    assert s["command"] == "stop" and s.get("paused") is False


def test_bad_token_rejected(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    authed_client.post(f"/sessions/{sid}/multicam/join-info")
    r = authed_client.post(
        f"/sessions/{sid}/multicam/register",
        json={"token": "wrong", "role": "camera", "label": "x"},
    )
    assert r.status_code == 403


def test_join_info_unknown_session_404(authed_client: TestClient) -> None:
    assert authed_client.post(f"/sessions/{uuid4()}/multicam/join-info").status_code == 404


def test_device_clip_upload(authed_client: TestClient, tmp_path, monkeypatch) -> None:
    from api.routes import capture_coord

    monkeypatch.setattr(capture_coord, "_VIDEO_DIR", tmp_path)
    sid = _make_session(authed_client)
    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    dev_id = authed_client.post(
        f"/sessions/{sid}/multicam/register",
        json={"token": token, "role": "camera", "label": "front"},
    ).json()["device_id"]

    r = authed_client.post(
        f"/sessions/{sid}/multicam/upload",
        data={"token": token, "device_id": dev_id},
        files={"file": ("clip.webm", b"\x1a\x45\xdf\xa3fake-clip", "video/webm")},
    )
    assert r.status_code == 200
    assert r.json()["bytes"] > 0
    assert any(tmp_path.iterdir())  # a per-device clip was written

    # The disk-scan clips listing surfaces it (works even without the in-memory roster).
    clips = authed_client.get(f"/sessions/{sid}/multicam/clips").json()
    assert any(c["device_id"] == dev_id and c["ext"] == "webm" for c in clips)

"""Session video — upload + serve the browser-recorded clip."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

# Import the route (pulls in store models) so the in-memory test DB has tables.
from api.routes import video as _video  # noqa: F401


def _make_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Vid"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def test_upload_then_serve(authed_client: TestClient, tmp_path, monkeypatch) -> None:
    from api.routes import video

    monkeypatch.setattr(video, "_VIDEO_DIR", tmp_path)
    sid = _make_session(authed_client)

    r = authed_client.post(
        f"/sessions/{sid}/video/upload",
        files={"file": ("capture.webm", b"\x1a\x45\xdf\xa3fake-webm-bytes", "video/webm")},
    )
    assert r.status_code == 200
    assert r.json()["bytes"] > 0

    got = authed_client.get(f"/sessions/{sid}/video")
    assert got.status_code == 200
    assert got.headers["content-type"] == "video/webm"
    assert got.content.endswith(b"fake-webm-bytes")


def test_serve_404_when_no_video(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    assert authed_client.get(f"/sessions/{sid}/video").status_code == 404


def test_upload_unknown_session_404(authed_client: TestClient, tmp_path, monkeypatch) -> None:
    from api.routes import video

    monkeypatch.setattr(video, "_VIDEO_DIR", tmp_path)
    r = authed_client.post(
        f"/sessions/{uuid4()}/video/upload",
        files={"file": ("c.webm", b"x", "video/webm")},
    )
    assert r.status_code == 404


def test_video_requires_auth(client: TestClient) -> None:
    assert client.get(f"/sessions/{uuid4()}/video").status_code == 401

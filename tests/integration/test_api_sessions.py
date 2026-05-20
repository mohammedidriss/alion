"""Sessions API — create / list / status / events flow.

The capture pipeline itself is not exercised here (would need mediapipe + a
video). We test the routes around it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_fighter(client: TestClient) -> str:
    r = client.post("/fighters", json={"name": "Test Fighter"})
    assert r.status_code == 201
    return r.json()["id"]


def test_create_and_list_session(authed_client: TestClient) -> None:
    fid = _make_fighter(authed_client)
    r = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"})
    assert r.status_code == 201
    sid = r.json()["id"]
    assert r.json()["status"] == "pending"

    r = authed_client.get("/sessions")
    assert r.status_code == 200
    assert any(s["id"] == sid for s in r.json())


def test_capture_status_for_idle_session(authed_client: TestClient) -> None:
    fid = _make_fighter(authed_client)
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    r = authed_client.get(f"/sessions/{sid}/capture/status")
    assert r.status_code == 200
    body = r.json()
    assert body["is_running"] is False
    assert body["punch_count"] == 0


def test_events_endpoint_empty_for_new_session(authed_client: TestClient) -> None:
    fid = _make_fighter(authed_client)
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    r = authed_client.get(f"/sessions/{sid}/events")
    assert r.status_code == 200
    assert r.json() == []


def test_upload_rejected_for_live_source(authed_client: TestClient) -> None:
    fid = _make_fighter(authed_client)
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    files = {"file": ("a.mp4", b"\x00" * 16, "video/mp4")}
    r = authed_client.post(f"/sessions/{sid}/upload", files=files)
    assert r.status_code == 400


def test_upload_attaches_path(authed_client: TestClient, tmp_path) -> None:  # type: ignore[no-untyped-def]
    fid = _make_fighter(authed_client)
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "uploaded_video"}).json()[
        "id"
    ]
    files = {"file": ("clip.mp4", b"\x00\x00\x00\x18ftypmp42", "video/mp4")}
    r = authed_client.post(f"/sessions/{sid}/upload", files=files)
    assert r.status_code == 200
    assert r.json()["video_path"] is not None


def test_bulk_events_endpoint(authed_client: TestClient) -> None:
    """POST /sessions/{id}/events/bulk — used by BrowserCapture on mobile/web."""
    fid = _make_fighter(authed_client)
    sid = authed_client.post(
        "/sessions", json={"fighter_id": fid, "source": "live_webcam"}
    ).json()["id"]

    events = [
        {
            "t_ms": 1000.0,
            "hand": "left",
            "velocity_ms": 2.5,
            "confidence": 0.8,
            "detected_by": "heuristic",
            "lead_or_rear": None,
            "velocity_source": "image_heuristic",
        },
        {
            "t_ms": 1500.0,
            "hand": "right",
            "velocity_ms": 3.1,
            "confidence": 0.9,
            "detected_by": "heuristic",
            "lead_or_rear": None,
            "velocity_source": "world",
        },
    ]

    r = authed_client.post(
        f"/sessions/{sid}/events/bulk",
        json={"events": events, "duration_ms": 5000.0},
    )
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] == 2

    # Events should now be retrievable
    stored = authed_client.get(f"/sessions/{sid}/events").json()
    assert len(stored) == 2

    # Session should be marked completed
    sess = authed_client.get(f"/sessions/{sid}").json()
    assert sess["status"] == "completed"
    assert sess["duration_ms"] == 5000.0

"""HRV API surface tests — status codes, validation, upload behavior.

End-to-end replay-through-thread is exercised in the unit tests for the
runner and replay driver. The thread uses store.get_session() against the
real engine, which doesn't share the in-memory test fixture; verifying the
threaded path here would require monkeypatching the engine singleton.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _make_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "HRV-test"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "hrv_replay"}).json()["id"]


def test_v2_hrv_start_400_when_no_csv_uploaded(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = authed_client.post(f"/v2/sessions/{sid}/hrv/start")
    assert r.status_code == 400
    assert "upload" in r.json()["detail"].lower()


def test_v2_hrv_upload_attaches_path(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = authed_client.post(
        f"/v2/sessions/{sid}/hrv/upload",
        files={"file": ("rr.csv", b"rr_ms\n800\n820\n810\n", "text/csv")},
    )
    assert r.status_code == 200
    body = r.json()
    assert "hrv_csv:" in (body.get("notes") or "")


def test_v2_hrv_unknown_session_404(authed_client: TestClient) -> None:
    bogus = "00000000-0000-0000-0000-000000000000"
    assert authed_client.get(f"/v2/sessions/{bogus}/hrv/samples").status_code == 404
    assert authed_client.get(f"/v2/sessions/{bogus}/hrv/status").status_code == 404
    assert authed_client.get(f"/v2/sessions/{bogus}/hrv/metrics").status_code == 404
    assert (
        authed_client.post(
            f"/v2/sessions/{bogus}/hrv/upload",
            files={"file": ("rr.csv", b"rr_ms\n800\n", "text/csv")},
        ).status_code
        == 404
    )


def test_v2_hrv_stop_409_when_nothing_running(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = authed_client.post(f"/v2/sessions/{sid}/hrv/stop")
    assert r.status_code == 409


def test_v2_hrv_status_shape_for_idle_session(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = authed_client.get(f"/v2/sessions/{sid}/hrv/status")
    assert r.status_code == 200
    body = r.json()
    assert {"session_id", "is_running", "sample_count", "metrics"} <= set(body.keys())
    assert body["is_running"] is False
    assert body["sample_count"] == 0


def test_v1_does_not_expose_hrv_routes(authed_client: TestClient) -> None:
    """ADR 004: /v1 is frozen. HRV is Phase 2 work, only mounted at /v2."""
    sid = _make_session(authed_client)
    assert authed_client.get(f"/v1/sessions/{sid}/hrv/samples").status_code == 404
    assert authed_client.get(f"/sessions/{sid}/hrv/samples").status_code == 404


def test_v2_hrv_samples_empty_for_new_session(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = authed_client.get(f"/v2/sessions/{sid}/hrv/samples")
    assert r.status_code == 200
    assert r.json() == []

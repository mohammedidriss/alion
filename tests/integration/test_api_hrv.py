"""HRV API surface tests — status codes, validation, upload behavior.

End-to-end replay-through-thread is exercised in the unit tests for the
runner and replay driver. The thread uses store.get_session() against the
real engine, which doesn't share the in-memory test fixture; verifying the
threaded path here would require monkeypatching the engine singleton.
"""

from __future__ import annotations

from typing import Any

import pytest
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


def _live_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Strap"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def _capture_start_ble(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Swap the Bluetooth thread for a recorder of how the stream was set up."""
    from api.services import hrv_runner

    got: dict[str, Any] = {}

    def fake_start_ble(session_id: object, address: str, factory: object, **kw: Any) -> bool:
        got.update(kw, address=address)
        return True

    monkeypatch.setattr(hrv_runner, "start_ble", fake_start_ble)
    return got


def test_an_armed_strap_stores_only_what_the_cameras_filmed(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.routes import capture_coord as cc
    from store import HRSampleRow

    now = [2_000_000.0]
    monkeypatch.setattr(cc, "_now_ms", lambda: now[0])
    got = _capture_start_ble(monkeypatch)
    sid = _live_session(authed_client)

    # The training-session page connects the paired strap as soon as it opens.
    r = authed_client.post(
        f"/v2/sessions/{sid}/hrv/ble/start", json={"address": "AA:BB", "arm": True}
    )
    assert r.status_code == 200
    assert got["wall_clock"] is True and callable(got["write_rows"])
    write = got["write_rows"]

    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    authed_client.post(
        f"/sessions/{sid}/multicam/register", json={"token": token, "label": "front"}
    )
    authed_client.post(f"/sessions/{sid}/multicam/start")
    t0 = now[0] + cc._START_DELAY_MS

    def beat(at: float) -> HRSampleRow:
        from uuid import UUID

        return HRSampleRow(session_id=UUID(sid), t_ms=at, rr_ms=600.0, hr_bpm=100.0)

    write([beat(t0 - 2_000), beat(t0 + 1_000), beat(t0 + 2_000)])
    samples = authed_client.get(f"/v2/sessions/{sid}/hrv/samples").json()
    assert [s["t_ms"] for s in samples] == [1_000, 2_000]  # the beat before Start is dropped


def test_start_finds_the_strap_already_connected(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import hrv_runner

    sid = _live_session(authed_client)
    monkeypatch.setattr(hrv_runner, "is_running", lambda _sid: True)
    r = authed_client.post(f"/v2/sessions/{sid}/hrv/ble/start", json={"address": "AA:BB"})
    assert r.status_code == 200 and r.json()["is_running"] is True  # no "already running" error


def test_a_session_without_cameras_keeps_the_straps_own_clock(
    authed_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    got = _capture_start_ble(monkeypatch)
    sid = _live_session(authed_client)
    r = authed_client.post(f"/v2/sessions/{sid}/hrv/ble/start", json={"address": "AA:BB"})
    assert r.status_code == 200
    assert got["wall_clock"] is False and got["write_rows"] is None

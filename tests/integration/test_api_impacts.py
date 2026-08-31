"""Head-impact upload/list API (ADR 007)."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

_CSV = (
    "t_ms,peak_linear_accel_g,peak_rotational_vel_rad_s,peak_rotational_accel_rad_s2,location,confidence,device_id\n"
    "850,38.2,16.1,2900,chin,0.90,MG-1\n"
    "2100,61.7,27.4,5600,left,0.97,MG-1\n"
    "3300,29.9,11.2,,front,,MG-1\n"
)


def _make_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Impact-test"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def _upload(client: TestClient, sid: str, body: str) -> object:
    return client.post(
        f"/v2/sessions/{sid}/impacts/upload",
        files={"file": ("impacts.csv", body.encode(), "text/csv")},
    )


def test_upload_then_list(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = _upload(authed_client, sid, _CSV)
    assert r.status_code == 200
    assert r.json() == 3

    rows = authed_client.get(f"/v2/sessions/{sid}/impacts").json()
    assert [x["t_ms"] for x in rows] == [850.0, 2100.0, 3300.0]
    assert rows[0]["location"] == "chin"
    assert rows[2]["peak_rotational_accel_rad_s2"] is None


def test_upload_replaces(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    _upload(authed_client, sid, _CSV)
    smaller = "t_ms,peak_linear_accel_g,peak_rotational_vel_rad_s,location\n10,20,8,back\n"
    assert _upload(authed_client, sid, smaller).json() == 1
    assert len(authed_client.get(f"/v2/sessions/{sid}/impacts").json()) == 1


def test_missing_required_column_422(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    bad = "t_ms,peak_linear_accel_g,location\n10,20,front\n"
    assert _upload(authed_client, sid, bad).status_code == 422


def test_unknown_session_404(authed_client: TestClient) -> None:
    assert _upload(authed_client, str(uuid4()), _CSV).status_code == 404
    assert authed_client.get(f"/v2/sessions/{uuid4()}/impacts").status_code == 404


def test_requires_auth(client: TestClient) -> None:
    assert client.get(f"/v2/sessions/{uuid4()}/impacts").status_code == 401

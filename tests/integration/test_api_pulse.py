"""rPPG pulse (PRV) estimate/list API (ADR 008)."""

from __future__ import annotations

import math
from uuid import uuid4

from fastapi.testclient import TestClient


def _rgb_trace_csv(bpm: float = 72.0, fps: float = 30.0, seconds: float = 12.0) -> str:
    freq = bpm / 60.0
    lines = ["r,g,b"]
    for i in range(int(fps * seconds)):
        g = 128.0 + 5.0 * math.sin(2 * math.pi * freq * (i / fps))
        lines.append(f"128,{g:.4f},128")
    return "\n".join(lines) + "\n"


def _make_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Pulse-test"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def _estimate(client: TestClient, sid: str, csv: str, fps: float = 30.0, extra: str = "") -> object:
    return client.post(
        f"/v2/sessions/{sid}/pulse/estimate?fps={fps}{extra}",
        files={"file": ("trace.csv", csv.encode(), "text/csv")},
    )


def test_estimate_then_list(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    r = _estimate(authed_client, sid, _rgb_trace_csv(), extra="&window_start_ms=8000")
    assert r.status_code == 200
    assert r.json() > 3  # several beats over 12 s

    rows = authed_client.get(f"/v2/sessions/{sid}/pulse").json()
    assert all(x["source"] == "rppg" for x in rows)  # PRV, not HRV
    assert all(x["t_ms"] >= 8000 for x in rows)  # tagged against window T_0
    mean_bpm = sum(x["pulse_bpm"] for x in rows) / len(rows)
    assert 60.0 <= mean_bpm <= 84.0  # recovered ~72 bpm


def test_bad_fps_422(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    assert _estimate(authed_client, sid, _rgb_trace_csv(), fps=0.0).status_code == 422


def test_missing_columns_422(authed_client: TestClient) -> None:
    sid = _make_session(authed_client)
    assert _estimate(authed_client, sid, "x,y\n1,2\n").status_code == 422


def test_unknown_session_404(authed_client: TestClient) -> None:
    assert _estimate(authed_client, str(uuid4()), _rgb_trace_csv()).status_code == 404
    assert authed_client.get(f"/v2/sessions/{uuid4()}/pulse").status_code == 404


def test_requires_auth(client: TestClient) -> None:
    assert client.get(f"/v2/sessions/{uuid4()}/pulse").status_code == 401

"""Live wrist IMUs over BLE — devices/owner and per-session start/stream/stop.

Bluetooth can't run in CI, so a fake recorder stands in for
`capture.imu.recorder`: it speaks the same JSON-line protocol, which is the
boundary the API depends on.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

FAKE_RECORDER = """
import json, signal, sys, time
hands = [a.split("=", 1)[0] for p, a in zip(sys.argv, sys.argv[1:]) if p == "--unit"]
stop = False
def _stop(*_):
    global stop
    stop = True
signal.signal(signal.SIGTERM, _stop)
def emit(o):
    print(json.dumps(o), flush=True)
for h in hands:
    emit({"k": "st", "h": h, "connected": True, "battery_v": 4.2})
t0 = time.time() * 1000 + 50
for i in range(300):
    if stop:
        break
    for h in hands:
        punch = i % 50 == 0
        emit({"k": "s", "h": h, "t": t0 + i * 10, "a": [0.0, 0.0, 6.0 if punch else 1.0], "g": [0, 0, 0]})
    time.sleep(0.002)
while not stop:
    time.sleep(0.05)
"""


@pytest.fixture
def imu_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.services import imu_devices, imu_runner

    devices = tmp_path / "devices.json"
    devices.write_text(json.dumps({"AAA": {"wrist": "left"}, "BBB": {"wrist": "right"}}))
    monkeypatch.setattr(imu_devices, "DEVICES_FILE", devices)
    fake = tmp_path / "fake_recorder.py"
    fake.write_text(FAKE_RECORDER)
    monkeypatch.setattr(imu_runner, "RECORDER_CMD", [sys.executable, str(fake)])
    yield devices


def _fighter(client: TestClient, name: str) -> str:
    return client.post("/fighters", json={"name": name}).json()["id"]


def _session(client: TestClient, fighter_id: str) -> str:
    return client.post(
        "/sessions", json={"fighter_id": fighter_id, "source": "live_webcam"}
    ).json()["id"]


def test_owner_is_set_and_reported(authed_client: TestClient, imu_setup: Path) -> None:
    fid = _fighter(authed_client, "Mohamad")
    before = authed_client.get("/v2/imu/devices").json()
    assert before["owner"] is None
    assert {u["hand"] for u in before["units"]} == {"left", "right"}

    after = authed_client.put("/v2/imu/devices/owner", json={"fighter_id": fid}).json()
    assert after["owner"] == {"fighter_id": fid, "name": "Mohamad"}
    # persisted alongside each unit's wrist
    saved = json.loads(imu_setup.read_text())
    assert all(m["fighter_id"] == fid and m["wrist"] for m in saved.values())


def test_stream_stores_both_wrists_on_the_owners_session(
    authed_client: TestClient, imu_setup: Path
) -> None:
    fid = _fighter(authed_client, "Mohamad")
    authed_client.put("/v2/imu/devices/owner", json={"fighter_id": fid})
    sid = _session(authed_client, fid)

    started = authed_client.post(f"/v2/sessions/{sid}/imu/ble/start")
    assert started.status_code == 200 and started.json()["running"] is True
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            units = authed_client.get(f"/v2/sessions/{sid}/imu/ble/status").json()["units"]
            if all(u["samples"] >= 250 for u in units.values()):
                break
            time.sleep(0.1)
        assert all(u["connected"] for u in units.values())
        assert all(u["peak_g"] >= 5.0 for u in units.values())  # the simulated punches
        assert all(u["battery_v"] == 4.2 and u["battery_pct"] == 100 for u in units.values())
    finally:
        stopped = authed_client.post(f"/v2/sessions/{sid}/imu/ble/stop").json()
    assert stopped["running"] is False and stopped["error"] is None

    rows = authed_client.get(f"/sessions/{sid}/imu/samples").json()
    assert {r["hand"] for r in rows} == {"left", "right"}
    assert all(r["t_ms"] >= 0 for r in rows)
    assert max(r["az_g"] for r in rows) == pytest.approx(6.0)


def test_refuses_another_fighters_session(authed_client: TestClient, imu_setup: Path) -> None:
    owner = _fighter(authed_client, "Mohamad")
    other = _fighter(authed_client, "John")
    authed_client.put("/v2/imu/devices/owner", json={"fighter_id": owner})
    r = authed_client.post(f"/v2/sessions/{_session(authed_client, other)}/imu/ble/start")
    assert r.status_code == 409 and "Mohamad" in r.json()["detail"]


def test_requires_configured_units_and_an_owner(authed_client: TestClient, imu_setup: Path) -> None:
    sid = _session(authed_client, _fighter(authed_client, "Mohamad"))
    no_owner = authed_client.post(f"/v2/sessions/{sid}/imu/ble/start")
    assert no_owner.status_code == 409 and "owner" in no_owner.json()["detail"]

    imu_setup.write_text("{}")
    no_units = authed_client.post(f"/v2/sessions/{sid}/imu/ble/start")
    assert no_units.status_code == 409 and "imu_tool" in no_units.json()["detail"]


def test_status_before_start_lists_idle_wrists(authed_client: TestClient, imu_setup: Path) -> None:
    sid = _session(authed_client, _fighter(authed_client, "Mohamad"))
    st = authed_client.get(f"/v2/sessions/{sid}/imu/ble/status").json()
    assert st["running"] is False
    assert set(st["units"]) == {"left", "right"}
    assert not any(u["connected"] for u in st["units"].values())


def test_devices_report_names(authed_client: TestClient, imu_setup: Path) -> None:
    imu_setup.write_text(
        json.dumps(
            {
                "AAA": {"wrist": "left", "name": "WT901BLE68"},
                "BBB": {"wrist": "right", "name": "WT901BLE68"},
            }
        )
    )
    units = authed_client.get("/v2/imu/devices").json()["units"]
    assert [(u["hand"], u["name"]) for u in units] == [
        ("left", "WT901BLE68"),
        ("right", "WT901BLE68"),
    ]


def test_check_connects_briefly_without_a_session(
    authed_client: TestClient, imu_setup: Path
) -> None:
    r = authed_client.post("/v2/imu/devices/check")
    assert r.status_code == 200
    body = r.json()
    assert body["running"] is False and body["error"] is None
    for unit in body["units"].values():
        assert unit["connected"] and unit["samples"] >= 300
        assert unit["battery_v"] == 4.2 and unit["peak_g"] >= 5.0


def test_paused_time_is_cut_from_the_timeline_like_the_video() -> None:
    """MediaRecorder drops paused time from the clip, so the IMU timeline must too."""
    import subprocess

    from api.services.imu_runner import _Job

    job = _Job(proc=subprocess.Popen([sys.executable, "-c", "pass"]), t0_ms=1000.0, units={})
    job.proc.wait()
    job.pauses = [(3000.0, 5000.0), (8000.0, None)]  # 2 s pause, then paused again
    assert job.timeline_ms(2000.0) == 1000.0  # before any pause: plain offset
    assert job.timeline_ms(4000.0) is None  # taken while paused → dropped
    assert job.timeline_ms(6000.0) == 3000.0  # after resume: shifted back by 2 s
    assert job.timeline_ms(9000.0) is None  # still paused

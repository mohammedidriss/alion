"""Counting punches right (ADR-059): the wrist sensors' live count, each camera's
view of the wrists, the trained counter in the cross-check, and a counter that
learns from every exported dataset."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from tests.integration.test_cross_check import _imu_rows
from tests.integration.test_training import _export


def test_the_live_reading_counts_each_wrists_punches(
    authed_client: TestClient, session: Session
) -> None:
    fid = authed_client.post("/fighters", json={"name": "Live", "stance": "orthodox"}).json()["id"]
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
        "id"
    ]
    assert authed_client.get(f"/v2/sessions/{sid}/live").json()["wrist_punches"] is None
    rows = _imu_rows(
        UUID(sid), {"right": [1000, 2000, 3000], "left": []}, {"right": 4000, "left": 4000}
    )
    session.add_all(rows)
    session.commit()
    assert authed_client.get(f"/v2/sessions/{sid}/live").json()["wrist_punches"] == {
        "left": 0,
        "right": 3,
    }
    # More arrive: only those are read, and the count grows.
    more = [r for r in _imu_rows(UUID(sid), {"right": [5000]}, {"right": 6000}) if r.t_ms >= 4000]  # type: ignore[attr-defined]
    session.add_all(more)
    session.commit()
    assert authed_client.get(f"/v2/sessions/{sid}/live").json()["wrist_punches"]["right"] == 4


def test_a_take_is_counted_from_its_csv_as_it_grows(tmp_path: Path) -> None:
    from uuid import uuid4

    from api.services import wrist_live

    folder = tmp_path / "take"
    folder.mkdir()
    csv = folder / "imu.csv"
    csv.write_text("t_ms,hand,ax_g,ay_g,az_g\n")
    tid = uuid4()

    def lines(start: int, end: int, punches: list[int]) -> str:
        out = []
        for t in range(start, end, 10):
            g = 6.0 if any(abs(t - p) < 40 for p in punches) else 1.0
            out.append(f"{t},left,0,0,{g}\n")
        return "".join(out)

    with csv.open("a") as f:
        f.write(lines(0, 3000, [1000, 2000]))
    assert wrist_live.take_counts(tid, folder) == {"left": 2, "right": 0}
    with csv.open("a") as f:
        f.write(lines(3000, 5000, [4000]) + "5000,le")  # a line still being written
    assert wrist_live.take_counts(tid, folder) == {"left": 3, "right": 0}


def test_each_camera_says_how_well_it_sees_the_wrists(authed_client: TestClient) -> None:
    fid = authed_client.post("/fighters", json={"name": "Cam", "stance": "orthodox"}).json()["id"]
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
        "id"
    ]
    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    dev = authed_client.post(
        f"/sessions/{sid}/multicam/register", json={"token": token, "label": "side"}
    ).json()["device_id"]
    quality = {"both": 0.35, "left": 1.0, "right": 0.35, "fps": 24.0}
    r = authed_client.post(
        f"/sessions/{sid}/multicam/heartbeat",
        json={"token": token, "device_id": dev, "status": "ready", "quality": quality},
    )
    assert r.status_code == 200, r.text
    (cam,) = authed_client.get(f"/sessions/{sid}/multicam/devices").json()
    assert cam["quality"] == quality


def test_the_counter_learns_from_every_dataset_and_counts_the_cameras(
    authed_client: TestClient, recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import dataset_store, punch_counter, training
    from capture.cv.writer import read_pose_parquet

    monkeypatch.setattr(dataset_store, "DATASETS_DIR", tmp_path / "datasets")
    monkeypatch.setattr(training, "MODELS_DIR", tmp_path / "models")
    monkeypatch.setattr(punch_counter, "MODELS_DIR", tmp_path / "models")
    one, two = (
        authed_client.post("/v2/datasets", json={"name": n, "protocol": "rq2-v1"}).json()["id"]
        for n in ("RQ2", "Single round")
    )
    _export(one)
    _export(two)
    alone = training.run(UUID(one), include_others=False)["data"]
    both = training.run(UUID(one))["data"]
    assert alone["other_datasets"] == [] and alone["train_stretches"] == 3
    (other,) = both["other_datasets"]
    assert other["dataset_id"] == two and other["stretches"] == 4
    assert both["train_stretches"] == 3 + 4 and both["test_stretches"] == 1

    # The newest counter now counts the cameras' punches in every cross-check.
    cur = punch_counter.current()
    assert cur is not None and cur["version"] == 2 and punch_counter.label() is not None
    pose = next((tmp_path / "datasets" / one / "export" / "takes").rglob("cam1.parquet"))
    found = punch_counter.camera_punches(read_pose_parquet(pose), stance="orthodox")
    assert found and all(e.detected_by == "custom_ml" for e in found)
    assert any(e.velocity_ms > 0 for e in found)
    shown = authed_client.get("/v2/punch-counter").json()["counter"]
    assert shown["version"] == 2 and shown["dataset_name"] == "RQ2"

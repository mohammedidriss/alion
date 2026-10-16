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

    # The capture starts over (its clock goes back to 0): the count starts over too.
    again = _imu_rows(UUID(sid), {"right": [1000]}, {"right": 2000, "left": 2000})
    session.add_all(again)
    session.commit()
    assert authed_client.get(f"/v2/sessions/{sid}/live").json()["wrist_punches"] == {
        "left": 0,
        "right": 1,
    }


def test_a_long_session_is_counted_once_not_over_and_over() -> None:
    """Counted piece by piece as it arrives, a long stream gives the same count as
    counting it all at once, and old samples are let go (ADR-064)."""
    import numpy as np

    from api.services import wrist_counter, wrist_live

    rng = np.random.default_rng(0)
    t = np.arange(0.0, 600_000.0, 10.0)  # 10 minutes at 100 Hz
    punches = np.arange(1000.0, 599_000.0, 1700.0)
    imu = np.zeros((len(t), 6))
    imu[:, 2] = 1.0
    for at in punches:
        near = np.abs(t - at) <= 60
        imu[near, 0] += 5.0 * (1 - np.abs(t[near] - at) / 60)
    imu += rng.normal(0, 0.03, imu.shape)
    whole = len(
        wrist_counter.find({"right": (t, imu), "left": (t, imu * [0, 0, 1, 0, 0, 0])})["right"]
    )
    st = wrist_live._Stream()
    for i in range(len(t)):
        wrist_live._add(st, "right", float(t[i]), tuple(imu[i]))
        wrist_live._add(st, "left", float(t[i]), (0.0, 0.0, float(imu[i, 2]), 0.0, 0.0, 0.0))
        if i % 150 == 0:  # a poll every 1.5 s
            wrist_live._count(st)
    assert wrist_live._count(st) == {"left": 0, "right": whole} and whole == len(punches)
    assert len(st.t["right"]) < 1000  # only the last few seconds are kept


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


def test_a_camera_counter_worse_than_the_detector_is_never_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-064: the newest counter by its report, and only one that beat the detector."""
    import json

    import joblib  # type: ignore[import-untyped]

    from api.services import punch_counter

    monkeypatch.setattr(punch_counter, "MODELS_DIR", tmp_path)
    punch_counter._cache.clear()
    d = tmp_path / "ds1"
    d.mkdir()

    def save(v: int, f1: float, when: str) -> None:
        joblib.dump({"model": None, "threshold": 0.5}, d / f"v{v}.joblib")
        report = {"created_at": when, "test": {"model": {"f1": f1}, "baseline": {"f1": 0.6}}}
        (d / f"v{v}.json").write_text(json.dumps(report))

    save(1, 0.8, "2026-10-01T00:00:00+00:00")
    save(2, 0.5, "2026-10-02T00:00:00+00:00")  # newer, but worse than the detector
    cur = punch_counter.current()
    assert cur is not None and cur["version"] == 1

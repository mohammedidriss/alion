"""Recorded training sessions train the models too (ADR-047): the punch counter on
the punches the wrists felt, moved onto each camera's clock; the punch-type models
on the sessions someone labelled. Sessions are trained on, never scored."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.integration import test_camera_type_model as cam_tests
from tests.integration import test_wrist_type_model as wrist_tests
from tests.integration.test_training import _export
from tests.unit.test_punch_model import synthetic, typed_schedule

pytest.importorskip("sklearn")

OFFSET_MS = 120.0  # the camera's clock runs this far ahead of the wrists'


def _recorded_session(
    recorded: Path,
    *,
    wrist: bool = True,
    matched: bool = True,
    gaps: dict[str, list[list[float]]] | None = None,
) -> str:
    """A cross-checked session: one camera's pose, and the punches the wrists felt."""
    from capture.cv.writer import write_pose_parquet

    sid = str(uuid4())
    processed = recorded / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    punches = typed_schedule(40, 1400)  # on the camera's clock
    write_pose_parquet(processed / f"{sid}.cam9.pose.parquet", synthetic(40, punches, seed=9))
    report = {
        "version": 4,
        "wrist": wrist,
        "wrist_gaps": gaps or {"left": [], "right": []},
        "cameras": [
            {"device_id": "cam9", "offset_ms": OFFSET_MS if matched else None, "drift_ppm": None}
        ],
        "punches": [
            {"t_ms": t - OFFSET_MS, "hand": h, "counted": True, "peak_g": 6.0}
            for t, h, _ in punches
        ]
        + [{"t_ms": 39_000.0, "hand": "left", "counted": True, "peak_g": None}],  # cameras only
    }
    (processed / f"{sid}.crosscheck.json").write_text(json.dumps(report))
    return sid


def test_the_counter_trains_on_recorded_sessions_and_is_scored_on_the_dataset_only(
    authed_client: TestClient, recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import dataset_store, training

    monkeypatch.setattr(dataset_store, "DATASETS_DIR", tmp_path / "datasets")
    monkeypatch.setattr(training, "MODELS_DIR", tmp_path / "models")
    sid = _recorded_session(recorded)
    _recorded_session(recorded, wrist=False)  # no wrists: nothing to learn from
    _recorded_session(recorded, matched=False)  # its clock never matched the wrists'

    did = authed_client.post("/v2/datasets", json={"name": "RQ2", "protocol": "rq2-v1"}).json()[
        "id"
    ]
    _export(did)
    (stretch,) = training._session_stretches(UUID(did))
    expected = [(t, h) for t, h, _ in typed_schedule(40, 1400)]
    assert stretch.take_id == f"session:{sid}" and stretch.labels == expected  # the camera's clock

    # Where a wrist stopped streaming, nothing is taught: the stretch is cut there.
    _recorded_session(recorded, gaps={"left": [], "right": [[10_000.0, 20_000.0]]})
    pieces = [s for s in training._session_stretches(UUID(did)) if s.take_id != stretch.take_id]
    shifted = (10_000.0 + OFFSET_MS, 20_000.0 + OFFSET_MS)
    assert len(pieces) == 2 and pieces[0].t_end == shifted[0] and pieces[1].t_start == shifted[1]
    assert not any(shifted[0] < t < shifted[1] for s in pieces for t, _ in s.labels)

    data = training.run(UUID(did))["data"]
    assert data["sessions"] == 2 and data["session_stretches"] == 3
    assert data["train_stretches"] == 3 + 3 and data["test_stretches"] == 1
    assert data["takes"] == 4  # the dataset's, as before


def test_labelled_sessions_teach_the_camera_type_model(
    recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import camera_type_model, dataset_store
    from capture.cv.writer import write_pose_parquet

    root = tmp_path / "datasets"
    for n in range(3):
        cam_tests._take(root, n)
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(camera_type_model, "MODEL_DIR", tmp_path / "models")
    sid = str(uuid4())
    punches = [(1500.0 + 1000.0 * i, h, k) for i, (h, k) in enumerate(cam_tests.SEQUENCE)]
    (recorded / "processed").mkdir(parents=True)
    write_pose_parquet(
        recorded / "processed" / f"{sid}.cam9.pose.parquet",
        synthetic(2.5 + len(punches), punches, seed=99),
    )
    (recorded / "labels").mkdir()
    (recorded / "labels" / f"{sid}.json").write_text(
        json.dumps([{"t_ms": t, "hand": h, "punch_type": k} for t, h, k in punches])
    )

    report = camera_type_model.train()
    assert report["data"]["takes"] == 3 and report["data"]["sessions"] == 1
    assert report["data"]["punches"] == 4 * len(cam_tests.SEQUENCE)


def test_labelled_sessions_teach_the_wrist_type_model(
    recorded: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import dataset_store, session_corpus, wrist_type_model

    root = tmp_path / "datasets"
    rng = np.random.default_rng(0)
    for n in range(3):
        wrist_tests._take(root, n, rng)
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(wrist_type_model, "MODEL_DIR", tmp_path / "models")
    # A session's wrist samples come from the database; here, a take's recording.
    wrist_tests._take(tmp_path / "session", 9, rng)
    folder = tmp_path / "session" / "ds" / "takes" / "take9"
    sid = str(uuid4())
    (recorded / "labels").mkdir(parents=True)
    (recorded / "labels" / f"{sid}.json").write_text((folder / "labels.json").read_text())
    streams = wrist_type_model._imu_streams(folder)
    monkeypatch.setattr(session_corpus, "imu_streams", lambda s: streams if s == sid else {})

    report = wrist_type_model.train()
    assert report["data"]["takes"] == 3 and report["data"]["sessions"] == 1
    assert report["data"]["punches"] == 4 * 24

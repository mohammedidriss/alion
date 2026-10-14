"""The cameras' punch-type model (ADR-034): trained from the takes' camera pose,
scored on takes it never saw (one camera, and all cameras together), versioned,
researcher-only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _signed_in
from tests.unit.test_punch_model import synthetic

pytest.importorskip("sklearn")

SEQUENCE = [("left", "jab"), ("right", "cross"), ("left", "hook"), ("right", "uppercut")] * 4


def _take(root: Path, n: int, person: str = "F-0001") -> None:
    from capture.cv.writer import write_pose_parquet

    folder = root / "ds" / "takes" / f"take{n}"
    (folder / "pose").mkdir(parents=True)
    punches = [(1500.0 + 1000.0 * i, hand, kind) for i, (hand, kind) in enumerate(SEQUENCE)]
    seconds = 2.5 + len(punches)
    for cam, seed in (("camA", 10 * n), ("camB", 10 * n + 1)):
        write_pose_parquet(folder / "pose" / f"{cam}.parquet", synthetic(seconds, punches, seed))
    (folder / "labels.json").write_text(
        json.dumps([{"t_ms": t, "hand": h, "punch_type": k} for t, h, k in punches])
    )
    (folder / "take.json").write_text(
        json.dumps({"take_id": f"take{n}", "status": "completed", "participant": person})
    )


@pytest.fixture
def takes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.services import camera_type_model, dataset_store

    root = tmp_path / "datasets"
    for n in range(4):
        _take(root, n)
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(camera_type_model, "MODEL_DIR", tmp_path / "models")
    yield root


def test_training_scores_on_held_out_takes_then_saves_a_version(takes: Path) -> None:
    from api.services import camera_type_model

    assert camera_type_model.current_version() is None and camera_type_model.latest_model() is None
    report = camera_type_model.train()
    assert report["version"] == 1 and camera_type_model.current_version() == 1
    assert report["data"]["takes"] == 4 and report["data"]["participants"] == 1
    assert report["data"]["punches"] == 4 * len(SEQUENCE)
    assert report["data"]["views"] == 2 * 4 * len(SEQUENCE)  # two cameras each
    assert report["held_out_views"]["accuracy"] > 0.9  # the motions are distinct here
    assert report["held_out_punches"]["accuracy"] > 0.9
    assert camera_type_model.latest_model() is not None
    assert camera_type_model.train()["version"] == 2


def test_only_researchers_train_or_read_it(authed_client: TestClient, takes: Path) -> None:
    other = _signed_in(authed_client, "coach3@alion.test", "Coach", "coach")
    as_coach = {"Authorization": f"Bearer {other}"}
    assert authed_client.post("/v2/camera-types/train", headers=as_coach).status_code == 403
    assert authed_client.get("/v2/camera-types", headers=as_coach).status_code == 403
    assert authed_client.get("/v2/camera-types").json() == {"report": None}
    r = authed_client.post("/v2/camera-types/train")
    assert r.status_code == 200 and r.json()["report"]["version"] == 1
    assert authed_client.get("/v2/camera-types").json()["report"]["version"] == 1


def test_too_few_takes_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services import camera_type_model, dataset_store

    root = tmp_path / "datasets"
    _take(root, 0)
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(camera_type_model, "MODEL_DIR", tmp_path / "models")
    with pytest.raises(ValueError, match="at least"):
        camera_type_model.train()


def test_with_two_people_each_is_scored_by_a_model_that_never_saw_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import camera_type_model, dataset_store

    root = tmp_path / "datasets"
    for n in range(4):
        _take(root, n, person="F-0001" if n < 2 else "F-0002")
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(camera_type_model, "MODEL_DIR", tmp_path / "models")
    report = camera_type_model.train()
    people = report["held_out_participants"]
    assert set(people["per_participant"]) == {"F-0001", "F-0002"} and people["accuracy"] > 0.8


def test_with_one_person_there_is_no_one_to_leave_out(takes: Path) -> None:
    from api.services import camera_type_model

    assert camera_type_model.train()["held_out_participants"] is None

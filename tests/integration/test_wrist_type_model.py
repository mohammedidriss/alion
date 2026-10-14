"""The wrist punch-type model (ADR-029): trained from the takes, scored on takes it
never saw, versioned, researcher-only, and naming punches with the stance."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.conftest import _signed_in

# Each motion's own signature: which axis the burst drives, which the forearm turns on.
SHAPE = {"jab": (0, 3), "cross": (0, 3), "hook": (1, 5), "uppercut": (2, 4)}


def _take(root: Path, n: int, rng: np.random.Generator) -> None:
    folder = root / "ds" / "takes" / f"take{n}"
    folder.mkdir(parents=True)
    labels, rows = [], []
    sequence = [("left", "jab"), ("right", "cross"), ("left", "hook"), ("right", "uppercut")] * 6
    t_end = 1000.0 + 1000.0 * len(sequence)
    punch_at = {}
    for i, (hand, kind) in enumerate(sequence):
        at = 1000.0 + 1000.0 * i
        punch_at[(hand, at)] = kind
        labels.append({"t_ms": at, "hand": hand, "punch_type": kind})
    for hand in ("left", "right"):
        for t in np.arange(0.0, t_end, 10.0):
            a = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
            for (h, at), kind in punch_at.items():
                if h == hand and abs(t - at) <= 60:
                    acc_axis, rot_axis = SHAPE[kind]
                    a[acc_axis] += 5.0 * (1 - abs(t - at) / 60)
                    a[rot_axis] += 900.0 * (1 - abs(t - at) / 60)
            a = [v + float(rng.normal(0, 0.05 if k < 3 else 5)) for k, v in enumerate(a)]
            rows.append([f"{t:.1f}", hand, *[f"{v:.4f}" for v in a]])
    with (folder / "imu.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_ms", "hand", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps"])
        w.writerows(rows)
    (folder / "labels.json").write_text(json.dumps(labels))
    (folder / "take.json").write_text(
        json.dumps(
            {
                "take_id": f"take{n}",
                "status": "completed",
                "participant": "F-0001",
                "stance": "orthodox",
                "block": None,
            }
        )
    )


@pytest.fixture
def takes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.services import dataset_store, wrist_type_model

    root = tmp_path / "datasets"
    rng = np.random.default_rng(0)
    for n in range(4):
        _take(root, n, rng)
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(wrist_type_model, "MODEL_DIR", tmp_path / "models")
    yield root


def test_training_scores_on_held_out_takes_then_saves_a_version(takes: Path) -> None:
    from api.services import wrist_type_model

    assert wrist_type_model.current_version() is None
    report = wrist_type_model.train()
    assert report["version"] == 1 and wrist_type_model.current_version() == 1
    assert report["data"]["takes"] == 4 and report["data"]["participants"] == 1
    assert report["held_out_takes"]["accuracy"] > 0.9  # the motions are distinct here
    assert wrist_type_model.latest_report()["version"] == 1  # type: ignore[index]
    assert wrist_type_model.train()["version"] == 2


def test_it_names_punches_with_the_stance(takes: Path) -> None:
    from api.services import wrist_type_model
    from api.services.wrist_type_model import _imu_streams

    t, imu = _imu_streams(takes / "ds" / "takes" / "take0")["left"]
    assert wrist_type_model.name(t, imu, [1000.0], "left", "orthodox") == [(None, None)]  # no model
    wrist_type_model.train()
    # take0, left wrist: a jab at 1 s, a hook at 3 s.
    named = wrist_type_model.name(t, imu, [1000.0, 3000.0], "left", "orthodox")
    assert named == [("straight", "jab"), ("hook", "hook")]
    t, imu = _imu_streams(takes / "ds" / "takes" / "take0")["right"]
    assert wrist_type_model.name(t, imu, [2000.0], "right", "orthodox") == [("straight", "cross")]
    assert wrist_type_model.name(t, imu, [2000.0], "right", "switch") == [("straight", None)]


def test_only_researchers_train_or_read_it(authed_client: TestClient, takes: Path) -> None:
    other = _signed_in(authed_client, "coach2@alion.test", "Coach", "coach")
    as_coach = {"Authorization": f"Bearer {other}"}
    assert authed_client.post("/v2/wrist-types/train", headers=as_coach).status_code == 403
    assert authed_client.get("/v2/wrist-types", headers=as_coach).status_code == 403
    assert authed_client.get("/v2/wrist-types").json() == {"report": None}
    r = authed_client.post("/v2/wrist-types/train")
    assert r.status_code == 200 and r.json()["report"]["version"] == 1
    assert authed_client.get("/v2/wrist-types").json()["report"]["version"] == 1


def test_too_few_takes_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services import dataset_store, wrist_type_model

    root = tmp_path / "datasets"
    _take(root, 0, np.random.default_rng(1))
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    monkeypatch.setattr(wrist_type_model, "MODEL_DIR", tmp_path / "models")
    with pytest.raises(ValueError, match="at least"):
        wrist_type_model.train()

"""The wrists' punch counter (ADR-060): learned from the labelled protocol blocks,
scored on takes it never saw next to the detector's fixed settings, and — once
trained — what counts every wrist punch: live, in a session, in the cross-check."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient

from tests.conftest import _signed_in

REPS = 12
STEP = 1000.0  # one punch a second


def _burst(t: float, at: float, g: float, axis: int, spin: float = 0.0) -> list[float]:
    """A 120 ms triangular burst of `g` on one axis (and a forearm turn), at `at`."""
    w = max(0.0, 1 - abs(t - at) / 60)
    a = [0.0] * 6
    a[axis] = g * w
    a[5] = spin * w
    return a


def _take(root: Path, n: int, rng: np.random.Generator) -> dict[str, list[float]]:
    """An orthodox take: a jab block (lead, left), a lead-hook block (sideways bursts
    with a turn — under the fixed 1.5 g once gravity is added), a rear-uppercut
    block (each punch's return to guard 430 ms later, nearly as tall), and a
    no-punch block where both hands shake as hard as a hook, without the turn.
    Returns the punches thrown, by block."""
    folder = root / "ds" / "takes" / f"take{n}"
    folder.mkdir(parents=True)
    blocks, labels = [], []
    events: dict[str, list[tuple[float, float, int, float]]] = {"left": [], "right": []}
    thrown: dict[str, list[float]] = {}
    t0 = 1000.0
    for key, hand, g, axis, spin, ret in (
        ("jab", "left", 5.0, 0, 0.0, None),
        ("lead_hook", "left", 2.2, 1, 900.0, None),
        ("rear_uppercut", "right", 5.0, 2, 0.0, 3.5),
        ("negatives", None, 0.0, 0, 0.0, None),
    ):
        start = t0
        thrown[key] = []
        for i in range(REPS):
            at = start + 500.0 + STEP * i + float(rng.normal(0, 30))
            if hand is None:  # shakes, both hands, no turn
                for h in ("left", "right"):
                    events[h].append((at + float(rng.normal(0, 80)), 2.0, 1, 0.0))
                continue
            events[hand].append((at, g, axis, spin))
            if ret is not None:
                events[hand].append((at + 430.0, ret, axis, 0.0))
            labels.append({"t_ms": round(at, 1), "hand": hand, "punch_type": key.split("_")[-1]})
            thrown[key].append(at)
        t0 = start + 500.0 + STEP * REPS + 500.0
        blocks.append({"key": key, "t_start_ms": start, "t_end_ms": t0})
        t0 += 500.0
    rows = []
    for hand in ("left", "right"):
        for t in np.arange(0.0, t0, 10.0):
            a = [0.0, 0.0, 1.0, 0.0, 0.0, 0.0]
            for at, g, axis, spin in events[hand]:
                if abs(t - at) <= 60:
                    a = [x + y for x, y in zip(a, _burst(t, at, g, axis, spin), strict=True)]
            a = [v + float(rng.normal(0, 0.03 if k < 3 else 4)) for k, v in enumerate(a)]
            rows.append([f"{t:.1f}", hand, *[f"{v:.4f}" for v in a]])
    with (folder / "imu.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["t_ms", "hand", "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps"])
        w.writerows(rows)
    (folder / "labels.json").write_text(json.dumps(labels))
    (folder / "protocol.json").write_text(json.dumps({"blocks": blocks}))
    (folder / "take.json").write_text(
        json.dumps(
            {
                "take_id": f"take{n}",
                "status": "completed",
                "participant": "F-0001",
                "stance": "orthodox",
            }
        )
    )
    return thrown


@pytest.fixture
def takes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.services import dataset_store

    root = tmp_path / "datasets"
    rng = np.random.default_rng(0)
    for n in range(4):
        _take(root, n, rng)
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    yield root


def _streams(folder: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    from api.services.wrist_type_model import _imu_streams

    return _imu_streams(folder)


def test_it_learns_what_the_fixed_settings_get_wrong(takes: Path) -> None:
    from api.services import wrist_counter

    assert wrist_counter.current_version() is None and wrist_counter.label() == "detector"
    report = wrist_counter.train()
    assert report["version"] == 1 and wrist_counter.label() == "wrist-counter v1"
    assert report["data"]["takes"] == 4
    held = report["held_out_takes"]
    fixed, counter = held["detector"]["by_block"], held["counter"]["by_block"]
    # The fixed settings miss the gentle hooks and count each uppercut twice…
    assert fixed["hook"]["found"] < fixed["hook"]["labelled"] / 2
    assert fixed["uppercut"]["found"] >= 1.8 * fixed["uppercut"]["labelled"]
    # …the counter, on takes it never saw, counts both right.
    for block in ("jab", "hook", "uppercut"):
        assert abs(counter[block]["found"] - counter[block]["labelled"]) <= 2, block
    assert counter["negative"]["on_idle_wrist"] <= 2
    assert held["counter"]["f1"] > held["detector"]["f1"] + 0.2
    assert wrist_counter.latest_report()["version"] == 1  # type: ignore[index]


def test_the_newest_counter_counts_live_and_in_sessions(takes: Path) -> None:
    from api.services import sensor_summary, wrist_counter, wrist_live

    folder = takes / "ds" / "takes" / "take0"
    streams = _streams(folder)
    before = wrist_counter.find(streams)
    assert len(before["right"]) == 2 * REPS  # fixed settings: every uppercut twice
    wrist_counter.train()
    after = wrist_counter.find(streams)
    assert abs(len(after["right"]) - REPS) <= 1
    assert abs(len(after["left"]) - 2 * REPS) <= 2  # the jabs and the hooks

    # Live, from the take's CSV.
    counts = wrist_live.take_counts(uuid4(), folder)
    assert counts == {"left": len(after["left"]), "right": len(after["right"])}

    # A session's numbers, from its sample rows.
    rows = []
    for hand, (t, imu) in streams.items():
        for ti, a in zip(t, imu, strict=True):
            rows.append(
                SimpleNamespace(
                    t_ms=float(ti),
                    hand=hand,
                    ax_g=a[0],
                    ay_g=a[1],
                    az_g=a[2],
                    gx_dps=a[3],
                    gy_dps=a[4],
                    gz_dps=a[5],
                )
            )
    events = sensor_summary.wrist_punch_events(rows)
    assert sum(e.hand == "right" for e in events) == len(after["right"])


def test_a_broken_model_falls_back_to_the_fixed_settings(takes: Path) -> None:
    from api.services import wrist_counter

    wrist_counter.MODEL_DIR.mkdir(parents=True)
    (wrist_counter.MODEL_DIR / "v1.joblib").write_bytes(b"not a model")
    report = {"held_out_takes": {"counter": {"f1": 0.9}, "detector": {"f1": 0.8}}}
    (wrist_counter.MODEL_DIR / "v1.json").write_text(json.dumps(report))
    found = wrist_counter.find(_streams(takes / "ds" / "takes" / "take0"))
    assert len(found["right"]) == 2 * REPS
    # …and it isn't named as the counter in use (a cross-check isn't saved under it).
    assert wrist_counter.label() == "detector" and wrist_counter.current_version() is None


def test_a_version_worse_than_the_fixed_settings_is_never_used(takes: Path) -> None:
    import shutil

    from api.services import wrist_counter

    wrist_counter.train()
    d = wrist_counter.MODEL_DIR
    shutil.copy(d / "v1.joblib", d / "v2.joblib")
    worse = json.loads((d / "v1.json").read_text())
    worse["version"] = 2
    worse["held_out_takes"]["counter"]["f1"] = worse["held_out_takes"]["detector"]["f1"] - 0.1
    (d / "v2.json").write_text(json.dumps(worse))
    assert wrist_counter.current_version() == 1


def test_only_researchers_train_or_read_it(authed_client: TestClient, takes: Path) -> None:
    other = _signed_in(authed_client, "coach3@alion.test", "Coach", "coach")
    as_coach = {"Authorization": f"Bearer {other}"}
    assert authed_client.post("/v2/wrist-counter/train", headers=as_coach).status_code == 403
    assert authed_client.get("/v2/wrist-counter", headers=as_coach).status_code == 403
    assert authed_client.get("/v2/wrist-counter").json() == {"report": None}
    r = authed_client.post("/v2/wrist-counter/train")
    assert r.status_code == 200 and r.json()["report"]["version"] == 1
    assert authed_client.get("/v2/wrist-counter").json()["report"]["version"] == 1


def test_too_few_takes_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services import dataset_store, wrist_counter

    root = tmp_path / "datasets"
    _take(root, 0, np.random.default_rng(1))
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", root)
    with pytest.raises(ValueError, match="at least"):
        wrist_counter.train()

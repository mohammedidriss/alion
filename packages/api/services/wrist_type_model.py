"""The wrist sensors' punch-type model (ADR-029): train, keep, use.

Trained on every completed dataset take's typed labels (read-only), straight
from the take folders — no export needed: each label (t_ms, hand, jab | cross |
hook | uppercut) gives one row of `analyze.wrist_types` features and its motion
(straight / hook / uppercut). Before the final fit it is scored on takes it never
saw (5-fold, grouped by take), and that score is saved with the model:

    data/ml/wrist_types/v{n}.joblib   the model
    data/ml/wrist_types/v{n}.json     its report

The newest version names the wrist punches in every cross-check (`name`); jab or
cross follows from the hand and the fighter's stance.
"""

from __future__ import annotations

import csv
import datetime
import json
import threading
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from analyze import wrist_types as wt
from api.services import dataset_store
from common import get_logger

log = get_logger(__name__)

MODEL_DIR = Path("data/ml/wrist_types")
# Other boxers to test on, when downloaded (ADR-029 update): Manoharan, "Boxing punch
# data", Zenodo doi:10.5281/zenodo.14965635, CC BY 4.0 — one CSV per punch type,
# gyr x/y/z (°/s) then acc x/y/z (g) at 200 Hz, read as orthodox (lead = left).
EXTERNAL = Path("data/external/zenodo_14965635_boxing_punch")
EXTERNAL_FILES = {
    "Lead_jab.csv": ("left", "straight"),
    "Rear_jab.csv": ("right", "straight"),
    "Lead_hook.csv": ("left", "hook"),
    "Rear_hook.csv": ("right", "hook"),
    "Lead_uppercut.csv": ("left", "uppercut"),
    "Rear_uppercut.csv": ("right", "uppercut"),
}
MIN_TAKES = 3  # fewer can't be scored on takes held out
FOLDS = 5

_lock = threading.Lock()
_cache: dict[str, Any] = {}  # path → (mtime, payload)
_training = threading.Lock()


class BusyError(RuntimeError):
    """A training run is already going."""


def _imu_streams(folder: Path) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    rows: dict[str, list[list[float]]] = {"left": [], "right": []}
    with (folder / "imu.csv").open(newline="") as f:
        for r in csv.DictReader(f):
            if r.get("hand") in rows:
                rows[r["hand"]].append(
                    [
                        float(r["t_ms"]),
                        float(r["ax_g"]),
                        float(r["ay_g"]),
                        float(r["az_g"]),
                        float(r.get("gx_dps") or 0.0),
                        float(r.get("gy_dps") or 0.0),
                        float(r.get("gz_dps") or 0.0),
                    ]
                )
    out = {}
    for h, rr in rows.items():
        a = np.array(sorted(rr), dtype=float).reshape(-1, 7)
        out[h] = (a[:, 0], a[:, 1:])
    return out


def typed_punches(
    datasets: Path | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Features, motion, hand, take id, block kind ("combo" / "single") of every
    typed label in the completed takes with wrist data — and what they came from."""
    root = datasets or dataset_store.DATASETS_DIR
    xs: list[np.ndarray] = []
    ys: list[str] = []
    hands: list[str] = []
    groups: list[str] = []
    kinds: list[str] = []
    participants: set[object] = set()
    stances: Counter[str] = Counter()
    for tj in sorted(root.glob("*/takes/*/take.json")):
        folder = tj.parent
        take = json.loads(tj.read_text())
        if take.get("status") != "completed" or not (folder / "imu.csv").exists():
            continue
        labels_file = folder / "labels.json"
        labels = json.loads(labels_file.read_text()) if labels_file.exists() else []
        typed = [lab for lab in labels if lab.get("punch_type") in wt.TYPE_TO_MOTION]
        if not typed:
            continue
        streams = _imu_streams(folder)
        kind = "combo" if str(take.get("block") or "").startswith("combo") else "single"
        before = len(ys)
        for lab in typed:
            t, imu = streams[lab["hand"]]
            win = wt.window(t, imu, float(lab["t_ms"])) if len(t) else None
            if win is None:
                continue
            xs.append(wt.features(win, lab["hand"]))
            ys.append(wt.TYPE_TO_MOTION[lab["punch_type"]])
            hands.append(lab["hand"])
            groups.append(str(take.get("take_id", folder.name)))
            kinds.append(kind)
        if len(ys) > before:
            participants.add(take.get("participant"))
            stances[str(take.get("stance"))] += 1
    meta = {
        "takes": len(set(groups)),
        "participants": len(participants - {None}),
        "stances": dict(stances),
    }
    return np.array(xs), np.array(ys), np.array(hands), np.array(groups), {**meta, "kinds": kinds}


def score(y: np.ndarray, pred: np.ndarray, hands: np.ndarray) -> dict[str, Any]:
    return {
        "punches": len(y),
        "accuracy": round(float(np.mean(y == pred)), 3),
        "recall": {
            c: round(float(np.mean(pred[y == c] == c)), 3) if np.any(y == c) else None
            for c in wt.MOTIONS
        },
        "confusion": {c: dict(Counter(pred[y == c].tolist())) for c in wt.MOTIONS},
        "by_hand": {
            h: round(float(np.mean(y[hands == h] == pred[hands == h])), 3)
            for h in ("left", "right")
            if np.any(hands == h)
        },
        "majority_share": round(Counter(y.tolist()).most_common(1)[0][1] / len(y), 3),
    }


def train(datasets: Path | None = None) -> dict[str, Any]:
    """Score on takes held out, fit on everything, save a new version; returns its report."""
    if not _training.acquire(blocking=False):
        raise BusyError
    try:
        return _train(datasets)
    finally:
        _training.release()


def _train(datasets: Path | None) -> dict[str, Any]:
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]
    from sklearn.model_selection import (  # type: ignore[import-untyped, import-not-found, unused-ignore]
        GroupKFold,
    )

    x, y, hands, groups, meta = typed_punches(datasets)
    kinds = np.array(meta.pop("kinds"))
    if meta["takes"] < MIN_TAKES or len(set(y.tolist())) < 2:
        raise ValueError(
            f"needs typed punches from at least {MIN_TAKES} takes with wrist data "
            f"(found {meta['takes']})"
        )
    pred = np.empty_like(y)
    for tr, te in GroupKFold(n_splits=min(FOLDS, meta["takes"])).split(x, y, groups):
        pred[te] = wt.classify(wt.fit(x[tr], y[tr]), x[te])
    held_out = score(y, pred, hands)
    combos = None
    single, combo = kinds == "single", kinds == "combo"
    if np.any(single) and np.any(combo) and len(set(y[single].tolist())) >= 2:
        combos = score(
            y[combo], np.array(wt.classify(wt.fit(x[single], y[single]), x[combo])), hands[combo]
        )

    model = wt.fit(x, y)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = 1 + max((int(p.stem[1:]) for p in MODEL_DIR.glob("v*.json")), default=0)
    joblib.dump(
        {"model": model, "version": version, "motions": wt.MOTIONS},
        MODEL_DIR / f"v{version}.joblib",
    )
    report = {
        "version": version,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "data": {**meta, "punches": len(y), "per_motion": dict(Counter(y.tolist()))},
        "held_out_takes": held_out,  # 5-fold, a take never in both fit and score
        "combos": combos,  # trained on single-type blocks, scored on combinations
        "other_boxers": other_boxers(model),  # a public set of boxers it never saw (or None)
    }
    (MODEL_DIR / f"v{version}.json").write_text(json.dumps(report, indent=2))
    log.info(
        "wrist_types.trained",
        extra={"_ctx_version": version, "_ctx_accuracy": held_out["accuracy"]},
    )
    return report


def external_stream(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """One external file as t_ms and (n, 6) ax, ay, az, gx, gy, gz at 100 Hz."""
    with path.open(newline="") as f:
        r = csv.reader(f)
        next(r)
        raw = np.array([[float(v) for v in row] for row in r if len(row) == 6])
    imu = np.concatenate([raw[:, 3:6], raw[:, 0:3]], axis=1)  # acceleration first, as here
    n = len(imu) // 2 * 2
    imu = imu[:n].reshape(-1, 2, 6).mean(axis=1)  # 200 → 100 Hz
    return np.arange(len(imu)) * 10.0, imu


def other_boxers(model: Any, root: Path | None = None) -> dict[str, Any] | None:
    """The model on boxers it never saw (the external set), with this project's own
    punch detector finding the punches — None when that set isn't downloaded."""
    from analyze.imu_punches import detect_punches

    folder = root or EXTERNAL
    if not all((folder / name).exists() for name in EXTERNAL_FILES):
        return None
    ys: list[str] = []
    preds: list[str] = []
    hands: list[str] = []
    for name, (hand, motion) in EXTERNAL_FILES.items():
        t, imu = external_stream(folder / name)
        found = detect_punches(t, imu[:, 0], imu[:, 1], imu[:, 2])
        rows = [wt.features(w, hand) for e in found if (w := wt.window(t, imu, e.t_ms)) is not None]
        if rows:
            preds += wt.classify(model, np.array(rows))
            ys += [motion] * len(rows)
            hands += [hand] * len(rows)
    if not ys:
        return None
    return {
        "dataset": "Zenodo 14965635 (Manoharan, CC BY 4.0)",
        **score(np.array(ys), np.array(preds), np.array(hands)),
    }


def latest_report() -> dict[str, Any] | None:
    files = sorted(MODEL_DIR.glob("v*.json"), key=lambda p: int(p.stem[1:]))
    if not files:
        return None
    data: dict[str, Any] = json.loads(files[-1].read_text())
    return data


def _latest_model() -> dict[str, Any] | None:
    files = sorted(MODEL_DIR.glob("v*.joblib"), key=lambda p: int(p.stem[1:]))
    if not files:
        return None
    path = files[-1]
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(str(path))
        if hit and hit[0] == mtime:
            payload: dict[str, Any] = hit[1]
            return payload
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]

    payload = joblib.load(path)
    with _lock:
        _cache.clear()
        _cache[str(path)] = (mtime, payload)
    return payload


def current_version() -> int | None:
    """The version the cross-checks name punches with (None: no model trained)."""
    files = [int(p.stem[1:]) for p in MODEL_DIR.glob("v*.joblib")]
    return max(files) if files else None


def name(
    t_ms: np.ndarray, imu: np.ndarray, at_ms: list[float], hand: str, stance: str | None
) -> list[tuple[str | None, str | None]]:
    """(motion, punch type) for each punch of one wrist — (None, None) where there's
    no model or the window is unusable. `imu` is (n, 6): ax, ay, az, gx, gy, gz."""
    payload = _latest_model()
    if payload is None or len(t_ms) == 0:
        return [(None, None) for _ in at_ms]
    rows, idx = [], []
    for i, at in enumerate(at_ms):
        win = wt.window(t_ms, imu, at)
        if win is not None:
            rows.append(wt.features(win, hand))
            idx.append(i)
    out: list[tuple[str | None, str | None]] = [(None, None) for _ in at_ms]
    if rows:
        for i, motion in zip(idx, wt.classify(payload["model"], np.array(rows)), strict=True):
            out[i] = (motion, wt.motion_to_type(motion, hand, stance))
    return out

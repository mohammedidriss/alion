"""The cameras' punch-type model (ADR-034): train, keep, use.

The ADR-020 classifier (`analyze.punch_model`: the arm's 3D motion relative to its
shoulder, from MediaPipe's world landmarks) trained straight from the dataset
takes — every completed take's typed labels, as each of its cameras saw them, no
export needed. Before the final fit it is scored on takes it never saw (5-fold,
grouped by take): one camera view at a time, and each punch with the views of
all its cameras averaged. Saved with that score:

    data/ml/camera_types/v{n}.joblib   the model
    data/ml/camera_types/v{n}.json     its report

The newest version names the punches in every cross-check (`proba`), with the
wrist model joining in when only one camera saw a punch (research branch
research/camera-wrist-fusion: one camera 95.1 %, with the wrist 96.6 %, three
cameras 97.5 %).
"""

from __future__ import annotations

import datetime
import json
import threading
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from analyze import punch_model
from analyze.wrist_types import MOTIONS, TYPE_TO_MOTION
from api.services import dataset_store
from capture.cv.writer import read_pose_parquet
from common import get_logger

log = get_logger(__name__)

MODEL_DIR = Path("data/ml/camera_types")
MIN_TAKES = 3
FOLDS = 5

_lock = threading.Lock()
_cache: dict[str, Any] = {}
_training = threading.Lock()


class BusyError(RuntimeError):
    """A training run is already going."""


@dataclass
class _Punch:
    take: str
    motion: str
    views: list[np.ndarray] = field(default_factory=list)
    person: str = ""


def _punches(datasets: Path | None = None) -> tuple[list[_Punch], dict[str, Any]]:
    root = datasets or dataset_store.DATASETS_DIR
    out: list[_Punch] = []
    participants: set[object] = set()
    for tj in sorted(root.glob("*/takes/*/take.json")):
        folder = tj.parent
        take = json.loads(tj.read_text())
        labels_file = folder / "labels.json"
        if take.get("status") != "completed" or not labels_file.exists():
            continue
        typed = [
            lab
            for lab in json.loads(labels_file.read_text())
            if lab.get("punch_type") in TYPE_TO_MOTION
        ]
        cams = sorted((folder / "pose").glob("*.parquet"))
        if not typed or not cams:
            continue
        mine = [
            _Punch(
                str(take.get("take_id", folder.name)),
                TYPE_TO_MOTION[lab["punch_type"]],
                person=str(take.get("participant") or ""),
            )
            for lab in typed
        ]
        for cam in cams:
            frames = read_pose_parquet(cam)
            if len(frames) < 10:
                continue
            tr = punch_model.track(frames)
            win = punch_model.arm_windows(tr)
            for p, lab in zip(mine, typed, strict=True):
                i = punch_model._frame(tr, float(lab["t_ms"]))
                if i is not None:
                    p.views.append(win[lab["hand"]][i])
        seen = [p for p in mine if p.views]
        if seen:
            participants.add(take.get("participant"))
            out += seen
    meta = {"takes": len({p.take for p in out}), "participants": len(participants - {None})}
    return out, meta


def proba(model: Any, rows: list[np.ndarray] | np.ndarray) -> np.ndarray:
    """Each row's class probabilities in MOTIONS order."""
    x = np.asarray(rows)
    p = model.predict_proba(x)
    classes = list(model.classes_)
    cols = [p[:, classes.index(m)] if m in classes else np.zeros(len(x)) for m in MOTIONS]
    return np.stack(cols, axis=1)


def _score(y: list[str], pred: list[str]) -> dict[str, Any]:
    ya, pa = np.array(y), np.array(pred)
    return {
        "punches": len(ya),
        "accuracy": round(float(np.mean(ya == pa)), 3),
        "recall": {
            m: round(float(np.mean(pa[ya == m] == m)), 3) if np.any(ya == m) else None
            for m in MOTIONS
        },
    }


def train(datasets: Path | None = None) -> dict[str, Any]:
    if not _training.acquire(blocking=False):
        raise BusyError
    try:
        return _train(datasets)
    finally:
        _training.release()


def _sample(p: list[_Punch]) -> list[punch_model.TypeSample]:
    return [
        punch_model.TypeSample(
            x=np.stack(q.views), y=np.array([q.motion] * len(q.views)), group=q.take
        )
        for q in p
    ]


def _train(datasets: Path | None) -> dict[str, Any]:
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]
    from sklearn.model_selection import (  # type: ignore[import-untyped, import-not-found, unused-ignore]
        GroupKFold,
    )

    punches, meta = _punches(datasets)
    if meta["takes"] < MIN_TAKES or len({p.motion for p in punches}) < 2:
        raise ValueError(
            f"needs typed punches from at least {MIN_TAKES} takes with camera pose (found {meta['takes']})"
        )
    groups = np.array([p.take for p in punches])
    view_y: list[str] = []
    view_pred: list[str] = []
    punch_y: list[str] = []
    punch_pred: list[str] = []
    folds = min(FOLDS, meta["takes"])
    for tr, te in GroupKFold(n_splits=folds).split(
        np.zeros(len(punches)), np.zeros(len(punches)), groups
    ):
        model = punch_model.fit_types(_sample([punches[i] for i in tr]))
        for i in te:
            pr = proba(model, punches[i].views)
            view_y += [punches[i].motion] * len(pr)
            view_pred += [MOTIONS[int(k)] for k in pr.argmax(axis=1)]
            punch_y.append(punches[i].motion)
            punch_pred.append(MOTIONS[int(pr.mean(axis=0).argmax())])
    # Each participant scored by a model that never saw them (ADR-044).
    by_person = None
    named = sorted({p.person for p in punches if p.person})
    if len(named) >= 2:
        py: list[str] = []
        pp: list[str] = []
        per: dict[str, float] = {}
        for person in named:
            train_p = [p for p in punches if p.person != person]
            test_p = [p for p in punches if p.person == person]
            if len({p.motion for p in train_p}) < 2:
                continue
            m = punch_model.fit_types(_sample(train_p))
            mine_y = [p.motion for p in test_p]
            mine_pred = [MOTIONS[int(proba(m, p.views).mean(axis=0).argmax())] for p in test_p]
            per[person] = round(float(np.mean(np.array(mine_y) == np.array(mine_pred))), 3)
            py += mine_y
            pp += mine_pred
        if py:
            by_person = {**_score(py, pp), "per_participant": per}

    model = punch_model.fit_types(_sample(punches))
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = 1 + max((int(p.stem[1:]) for p in MODEL_DIR.glob("v*.json")), default=0)
    joblib.dump({"model": model, "version": version}, MODEL_DIR / f"v{version}.joblib")
    report = {
        "version": version,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "data": {
            **meta,
            "punches": len(punches),
            "views": sum(len(p.views) for p in punches),
            "per_motion": dict(Counter(p.motion for p in punches)),
        },
        "held_out_views": _score(view_y, view_pred),  # one camera at a time
        "held_out_punches": _score(punch_y, punch_pred),  # all the punch's cameras averaged
        "held_out_participants": by_person,  # each person left out in turn (None: one person)
    }
    (MODEL_DIR / f"v{version}.json").write_text(json.dumps(report, indent=2))
    log.info("camera_types.trained", extra={"_ctx_version": version})
    return report


def latest_report() -> dict[str, Any] | None:
    files = sorted(MODEL_DIR.glob("v*.json"), key=lambda p: int(p.stem[1:]))
    if not files:
        return None
    data: dict[str, Any] = json.loads(files[-1].read_text())
    return data


def current_version() -> int | None:
    files = [int(p.stem[1:]) for p in MODEL_DIR.glob("v*.joblib")]
    return max(files) if files else None


def latest_model() -> Any | None:
    """The newest version's classifier (None: never trained)."""
    files = sorted(MODEL_DIR.glob("v*.joblib"), key=lambda p: int(p.stem[1:]))
    if not files:
        return None
    path = files[-1]
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(str(path))
        if hit and hit[0] == mtime:
            return hit[1]
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]

    payload = joblib.load(path)
    with _lock:
        _cache.clear()
        _cache[str(path)] = (mtime, payload["model"])
    return payload["model"]

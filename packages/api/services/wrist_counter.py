"""The wrist sensors' punch counter (ADR-060): train, keep, use.

Counts punches from the wrists without knowing their type (`analyze.wrist_counter`):
a sensitive detector's candidates, each kept or dropped by a classifier. It learns
from the labelled dataset takes, read-only, straight from the take folders:

- typed blocks: the labels (found with the type's own profile, so hooks and
  uppercuts are right) on the punching wrist; the other wrist punches nothing;
- the no-punch block: nothing on either wrist;
- combo blocks where every combo came out whole: their labels.

Free shadowboxing sits out — its labels come from the default detector, the one
this replaces. Before the final fit it is scored on takes it never saw (5-fold,
grouped by take) next to that detector, per kind of block, and the threshold is
chosen there:

    data/ml/wrist_counter/v{n}.joblib   the model and its threshold
    data/ml/wrist_counter/v{n}.json     its report

The newest version counts every wrist punch — live, in the cross-check, in a
session's numbers; with none, the detector's defaults do (`imu_punches`).
"""

from __future__ import annotations

import datetime
import json
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from analyze import wrist_counter as wc
from analyze.imu_punches import THRESHOLD_G, ImuPunch, detect_punches
from api.services import dataset_protocol as proto
from api.services import dataset_store, model_files
from api.services.wrist_type_model import _imu_streams
from common import get_logger

log = get_logger(__name__)

MODEL_DIR = Path("data/ml/wrist_counter")
MIN_TAKES = 3  # fewer can't be scored on takes held out
FOLDS = 5
THRESHOLDS = (0.3, 0.4, 0.5, 0.6, 0.7)
MIN_SAMPLES = 20

_lock = threading.Lock()
_cache: dict[str, Any] = {}  # path → (mtime, payload)
_training = threading.Lock()


class BusyError(RuntimeError):
    """A training run is already going."""


@dataclass(eq=False)
class Stretch:
    """One wrist over one block: its candidates and what's true there."""

    take: str
    group: str  # jab / cross / hook / uppercut / combo / negative
    punching: bool  # this wrist is meant to punch here
    truth: list[float]
    detector: list[float]  # what the default detector found
    cands: list[ImuPunch]
    rows: np.ndarray
    idx: list[int]
    y: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=int))


def _block_group(spec: proto.BlockSpec) -> str | None:
    if spec.kind == "free":
        return None
    if spec.kind in ("combo", "negative"):
        return spec.kind
    return spec.punch_type


def corpus(datasets: Path | None = None) -> tuple[list[Stretch], dict[str, Any]]:
    """Every labelled stretch of every completed take with wrist data."""
    root = datasets or dataset_store.DATASETS_DIR
    out: list[Stretch] = []
    takes: set[str] = set()
    people: set[str] = set()
    for tj in sorted(root.glob("*/takes/*/take.json")):
        folder = tj.parent
        take = json.loads(tj.read_text())
        labels_file = proto.labels_path(folder)
        if (
            take.get("status") != "completed"
            or not (folder / "imu.csv").exists()
            or not labels_file.exists()
        ):
            continue
        data = proto.load(folder)
        labels = json.loads(labels_file.read_text())
        # imu.csv is raw; the labels are corrected (sensors worn swapped)
        streams = _imu_streams(folder, swapped=proto.hands_swapped(data))
        tid = str(take.get("take_id", folder.name))
        # Candidates and their features from each wrist's whole stream, so one at a
        # block's edge sees its real neighbours, as it does when a round is counted.
        whole: dict[str, tuple[list[ImuPunch], np.ndarray, list[int]]] = {}
        for hand in ("left", "right"):
            t, imu = streams[hand]
            cands_all = wc.candidates(t, imu)
            rows_all, idx_all = wc.rows(
                (t, imu), hand, cands_all, streams["right" if hand == "left" else "left"]
            )
            whole[hand] = (cands_all, rows_all, idx_all)
        for b in data["blocks"]:
            if b.get("discarded") or b.get("t_end_ms") is None or b["key"] not in proto.SPECS:
                continue
            spec = proto.SPECS[b["key"]]
            group = _block_group(spec)
            if group is None or (spec.kind == "combo" and (b.get("off_hand") or 0) > 0):
                continue  # free shadowboxing, or a combo block with unlabelled punches
            wanted = (
                proto.expected_hands(spec, take.get("stance")) if group != "negative" else set()
            )
            t0, t1 = float(b["t_start_ms"]), float(b["t_end_ms"])
            for hand in ("left", "right"):
                t, imu = streams[hand]
                inside = (t >= t0) & (t <= t1)
                if int(inside.sum()) < MIN_SAMPLES:
                    continue
                ti, ii = t[inside], imu[inside]
                truth = sorted(
                    float(lab["t_ms"])
                    for lab in labels
                    if lab["hand"] == hand and t0 <= lab["t_ms"] <= t1 and hand in wanted
                )
                cands_all, rows_all, idx_all = whole[hand]
                pos = [k for k, c in enumerate(cands_all) if t0 <= c.t_ms <= t1]
                local = {k: i for i, k in enumerate(pos)}
                cands = [cands_all[k] for k in pos]
                keep_rows = [r for r, k in enumerate(idx_all) if k in local]
                rows = rows_all[keep_rows] if keep_rows else np.zeros((0, wc.N_FEATURES))
                idx = [local[idx_all[r]] for r in keep_rows]
                hit = wc.matched([c.t_ms for c in cands], truth)
                out.append(
                    Stretch(
                        take=tid,
                        group=group,
                        punching=hand in wanted,
                        truth=truth,
                        detector=[e.t_ms for e in detect_punches(ti, ii[:, 0], ii[:, 1], ii[:, 2])],
                        cands=cands,
                        rows=rows,
                        idx=idx,
                        y=np.array([1 if k in hit else 0 for k in idx], dtype=int),
                    )
                )
                takes.add(tid)
                people.add(str(take.get("participant") or ""))
    return out, {"takes": len(takes), "participants": len(people - {""})}


def _fit(x: np.ndarray, y: np.ndarray) -> Any:
    from sklearn.ensemble import (  # type: ignore[import-untyped, import-not-found, unused-ignore]
        HistGradientBoostingClassifier,
    )

    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0).fit(
        x, y
    )


def _score(found: list[list[float]], stretches: list[Stretch]) -> dict[str, Any]:
    """Overall and per kind of block: found and right on the punching wrist, and
    what was found on a wrist that wasn't punching."""
    per: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])  # found, truth, right, idle
    tp = fp = fn = 0
    for f, s in zip(found, stretches, strict=True):
        right = len(wc.matched(f, s.truth))
        r = per[s.group]
        if s.punching:
            r[0] += len(f)
            r[1] += len(s.truth)
            r[2] += right
        else:
            r[3] += len(f)
        tp, fp, fn = tp + right, fp + len(f) - right, fn + len(s.truth) - right

    def f1(right: int, found_n: int, truth: int) -> float:
        return round(2 * right / (found_n + truth), 3) if found_n + truth else 1.0

    p = tp / (tp + fp) if tp + fp else 0.0
    r_ = tp / (tp + fn) if tp + fn else 0.0
    return {
        "f1": round(2 * p * r_ / (p + r_), 3) if p + r_ else 0.0,
        "precision": round(p, 3),
        "recall": round(r_, 3),
        "by_block": {
            g: {
                "found": v[0],
                "labelled": v[1],
                "f1": f1(v[2], v[0], v[1]),
                "on_idle_wrist": v[3],
            }
            for g, v in sorted(per.items())
        },
    }


def _kept(s: Stretch, probs: np.ndarray, threshold: float) -> list[float]:
    # As `wc.find`: a candidate without a usable window is judged by its height.
    p = {k: (1.0 if c.peak_g >= THRESHOLD_G else 0.0) for k, c in enumerate(s.cands)}
    p |= dict(zip(s.idx, probs.tolist(), strict=True))
    return [c.t_ms for c in wc.keep(s.cands, p, threshold)]


def train(datasets: Path | None = None) -> dict[str, Any]:
    """Score on takes held out, fit on everything, save a new version; returns its report."""
    if not _training.acquire(blocking=False):
        raise BusyError
    try:
        return _train(datasets)
    finally:
        _training.release()


def _train(datasets: Path | None) -> dict[str, Any]:
    from sklearn.model_selection import (  # type: ignore[import-untyped, import-not-found, unused-ignore]
        GroupKFold,
    )

    stretches, meta = corpus(datasets)
    usable = [s for s in stretches if len(s.idx)]
    if meta["takes"] < MIN_TAKES or not usable:
        raise ValueError(
            f"needs labelled protocol blocks from at least {MIN_TAKES} takes with wrist data "
            f"(found {meta['takes']})"
        )
    x = np.concatenate([s.rows for s in usable])
    y = np.concatenate([s.y for s in usable])
    if len(set(y.tolist())) < 2:
        raise ValueError("the labelled takes need punches and non-punches to learn from")
    groups = np.concatenate([[s.take] * len(s.idx) for s in usable])
    owner = np.concatenate([[i] * len(s.idx) for i, s in enumerate(usable)])

    # Each take scored by a model that never saw it.
    held = np.zeros(len(y))
    n_takes = len(set(groups.tolist()))
    for tr, te in GroupKFold(n_splits=min(FOLDS, n_takes)).split(x, y, groups):
        held[te] = _fit(x[tr], y[tr]).predict_proba(x[te])[:, 1]
    probs_of = {id(s): held[owner == i] for i, s in enumerate(usable)}

    def counted(threshold: float) -> list[list[float]]:
        return [
            _kept(s, probs_of[id(s)], threshold) if id(s) in probs_of else [] for s in stretches
        ]

    scores = {th: _score(counted(th), stretches) for th in THRESHOLDS}
    threshold = max(THRESHOLDS, key=lambda th: (scores[th]["f1"], -abs(th - 0.5)))

    model = _fit(x, y)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    version = 1 + max((int(p.stem[1:]) for p in MODEL_DIR.glob("v*.json")), default=0)
    report = {
        "version": version,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "threshold": threshold,
        "data": {
            **meta,
            "stretches": len(stretches),
            "punches": sum(len(s.truth) for s in stretches),
            "candidates": len(y),
            "per_block": dict(
                Counter(s.group for s in stretches if s.punching or s.group == "negative")
            ),
        },
        # 5-fold, a take never in both fit and score; next to the detector's defaults.
        "held_out_takes": {
            "counter": scores[threshold],
            "detector": _score([s.detector for s in stretches], stretches),
        },
    }
    # The report first, then the model: a version is in use once both are whole.
    model_files.write_json(report, MODEL_DIR / f"v{version}.json")
    model_files.dump(
        {"model": model, "version": version, "threshold": threshold},
        MODEL_DIR / f"v{version}.joblib",
    )
    log.info(
        "wrist_counter.trained",
        extra={"_ctx_version": version, "_ctx_f1": scores[threshold]["f1"]},
    )
    return report


def latest_report() -> dict[str, Any] | None:
    files = sorted(MODEL_DIR.glob("v*.json"), key=lambda p: int(p.stem[1:]))
    if not files:
        return None
    data: dict[str, Any] = json.loads(files[-1].read_text())
    return data


def _beats_detector(path: Path) -> bool:
    """A version is used only if, held out, it counted better than the fixed settings."""
    try:
        held = json.loads(path.with_suffix(".json").read_text())["held_out_takes"]
        return bool(held["counter"]["f1"] >= held["detector"]["f1"])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _latest_model() -> dict[str, Any] | None:
    """The newest version that beats the fixed settings and loads — None: count with
    the fixed settings. A file that fails to load is remembered as failed, not
    retried (and logged) on every count, until it changes."""
    files = sorted(
        (p for p in MODEL_DIR.glob("v*.joblib") if _beats_detector(p)),
        key=lambda p: int(p.stem[1:]),
    )
    if not files:
        return None
    path = files[-1]
    mtime = path.stat().st_mtime
    with _lock:
        hit = _cache.get(str(path))
        if hit and hit[0] == mtime:
            cached: dict[str, Any] | None = hit[1]
            return cached
    import joblib  # type: ignore[import-untyped, import-not-found, unused-ignore]

    loaded: dict[str, Any] | None
    try:
        loaded = joblib.load(path)
        float(loaded["threshold"])
    except Exception:
        log.exception("wrist_counter.unreadable", extra={"_ctx_path": str(path)})
        loaded = None
    with _lock:
        _cache.clear()
        _cache[str(path)] = (mtime, loaded)
    return loaded


def current_version() -> int | None:
    """The version counting the wrists' punches (None: the detector's defaults)."""
    payload = _latest_model()
    return int(payload["version"]) if payload is not None else None


def label() -> str:
    """What counts the wrists — the version that actually loaded, so a cross-check
    made while a model was unreadable doesn't carry that model's name."""
    v = current_version()
    return f"wrist-counter v{v}" if v else "detector"


def find(streams: dict[str, wc.Stream]) -> dict[str, list[ImuPunch]]:
    """Each wrist's punches: by the newest trained counter, or the detector's
    defaults without one (or if it fails). `streams`: hand → (t_ms sorted, (n, 6)
    ax, ay, az, gx, gy, gz); a wrist with too few samples finds nothing."""
    usable = {h: s for h, s in streams.items() if len(s[0]) >= MIN_SAMPLES}
    out: dict[str, list[ImuPunch]] = {h: [] for h in streams}
    payload = _latest_model()
    if payload is not None:
        try:
            return {**out, **wc.find(payload["model"], float(payload["threshold"]), usable)}
        except Exception:  # a model that fails here mustn't stop the counting
            log.exception("wrist_counter.failed")
    for hand, (t, imu) in usable.items():
        out[hand] = detect_punches(t, imu[:, 0], imu[:, 1], imu[:, 2])
    return out

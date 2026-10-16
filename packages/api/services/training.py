"""Train the camera punch counter — and its punch-type classifier — on a dataset's
export (analyze.punch_model).

Reads the dataset's export manifest (dataset_export: its takes, their pose and
labels, and the split — which stretches of which takes are for training and
which for testing), builds training rows from every camera's pose in the train
stretches, picks the probability threshold by cross-validation over takes (a
take is never split between fit and score), fits the final model on all train
stretches, and scores it on the test stretches — next to the current heuristic
counter (`punch_fusion.camera_punches`, as the browser cameras run it), the
baseline it has to beat. Labels come from the wrist sensors, so neither counter
is graded against itself.

Every cross-checked training session recorded with the wrists and cameras joins
the training stretches too (ADR-047, `session_corpus`): the punches the wrists
felt, moved onto each camera's clock. Sessions never join the test stretches, so
the scores stay the dataset's.

A second classifier names each punch — jab, cross, hook or uppercut (ADR-020). It
trains on the labelled punches of the train stretches and is scored on the test
stretches' typed punches two ways: given the true punch (each label's moment) next
to the current rule-based namer (`classify_punch_type`), and end to end (the
counter's own punches that match a label).

Training takes a few minutes, so it runs in a background thread. The model and
its report land in data/ml/punch_counter/{dataset}/: v{n}.joblib and v{n}.json.
"""

from __future__ import annotations

import datetime
import json
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

import numpy as np

from analyze import classify_punch_type, punch_model
from analyze.punch_fusion import camera_punches
from api.services import dataset_export, dataset_store, model_files, session_corpus
from common import get_logger
from contracts import Hand, Landmark, PoseFrame, WorldLandmark
from studies import DetectedPunch, match_events
from studies.evaluation import GroundTruthPunch

log = get_logger(__name__)

MODELS_DIR = Path("data/ml/punch_counter")
THRESHOLDS = tuple(round(x, 2) for x in np.arange(0.3, 0.96, 0.05))
TOLERANCE_MS = 200.0
SESSION_MARGIN_MS = 2000.0  # pose kept around a session's first and last punch
SESSION_MIN_MS = 5000.0  # a shorter piece between a session's wrist gaps is left out
BACKGROUND = True  # tests switch the thread off and call run()

_lock = threading.Lock()
_status: dict[str, dict[str, Any]] = {}  # dataset id → {running, step, error}


@dataclass
class Pose:
    """One camera's pose as arrays: time, image landmarks (n, 33, 4) and world
    landmarks (n, 33, 4), NaN where a frame had none."""

    t: np.ndarray
    lm: np.ndarray
    wl: np.ndarray

    def frames(self, t_start: float, t_end: float, capture: UUID) -> list[PoseFrame]:
        """`PoseFrame`s for one stretch (the heuristic baseline needs them)."""
        out: list[PoseFrame] = []
        for i in np.flatnonzero((self.t >= t_start) & (self.t <= t_end)):
            world = None
            if not np.isnan(self.wl[i, 0, 0]):
                world = tuple(
                    WorldLandmark.model_construct(x=x, y=y, z=z, visibility=v)
                    for x, y, z, v in self.wl[i].tolist()
                )
            out.append(
                PoseFrame.model_construct(
                    session_id=capture,
                    frame_index=len(out),
                    t_ms=float(self.t[i]),
                    landmarks=tuple(
                        Landmark.model_construct(x=x, y=y, z=z, visibility=v)
                        for x, y, z, v in self.lm[i].tolist()
                    ),
                    world_landmarks=world,
                )
            )
        return out


def read_pose(path: Path) -> Pose:
    """A pose parquet straight into arrays (reading it as `PoseFrame`s takes far
    longer for a long take)."""
    import pyarrow.parquet as pq

    table = pq.read_table(path)  # type: ignore[no-untyped-call]
    cols = set(table.column_names)

    def block(prefix: str) -> np.ndarray:
        n = table.num_rows
        out = np.full((n, 33, 4), np.nan)
        for i in range(33):
            for k, axis in enumerate("xyzv"):
                name = f"{prefix}{i:02d}_{axis}"
                if name in cols:
                    out[:, i, k] = table.column(name).to_numpy(zero_copy_only=False)
        return out

    t = table.column("t_ms").to_numpy(zero_copy_only=False).astype(float)
    return Pose(t=t, lm=block("lm"), wl=block("wl"))


@dataclass
class Stretch:
    """A labelled stretch of a take (one protocol block) and its cameras' pose."""

    take_id: str
    block: str
    t_start: float
    t_end: float
    labels: list[tuple[float, Hand]]
    tracks: dict[str, punch_model.Track]  # camera → smoothed pose, for the model
    poses: dict[str, Pose] = field(default_factory=dict)  # raw pose, for the baseline
    typed: list[tuple[float, Hand, str]] = field(default_factory=list)  # labels with a type
    stance: str | None = None

    def truth(self) -> list[GroundTruthPunch]:
        return [GroundTruthPunch(t_ms=t, hand=h) for t, h in self.labels]


TYPES = ("jab", "cross", "hook", "uppercut")


@dataclass
class TypeTally:
    """Punch naming: how many named right, per type, and what each was taken for."""

    right: int = 0
    total: int = 0
    unnamed: int = 0  # no pose near the punch, or the namer gave up
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)  # label → named → n

    def add(self, label: str, named: str | None) -> None:
        if named is None:
            self.unnamed += 1
            return
        self.total += 1
        self.right += int(named == label)
        row = self.confusion.setdefault(label, {})
        row[named] = row.get(named, 0) + 1

    def out(self) -> dict[str, Any]:
        per_type = {
            t: round(self.confusion[t].get(t, 0) / sum(self.confusion[t].values()), 3)
            for t in TYPES
            if t in self.confusion
        }
        return {
            "accuracy": round(self.right / self.total, 3) if self.total else None,
            "punches": self.total,
            "unnamed": self.unnamed,
            "per_type": per_type,  # of each type thrown, the share named right
            "confusion": self.confusion,
        }


@dataclass
class Tally:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    runs: int = 0  # camera × stretch evaluations
    counted: int = 0
    truth: int = 0

    def add(self, truth: list[GroundTruthPunch], found: list[DetectedPunch]) -> None:
        m = match_events(truth, found, TOLERANCE_MS)
        self.tp += m.true_positives
        self.fp += m.false_positives
        self.fn += m.false_negatives
        self.runs += 1
        self.counted += len(found)
        self.truth += len(truth)

    def out(self) -> dict[str, Any]:
        p = self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0
        r = self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0
        f1 = 2 * p * r / (p + r) if p + r else 0.0
        return {
            "precision": round(p, 3),
            "recall": round(r, 3),
            "f1": round(f1, 3),
            # per camera, on average: what it counted vs the punches thrown
            "counted": round(self.counted / self.runs, 1) if self.runs else 0,
            "truth": round(self.truth / self.runs, 1) if self.runs else 0,
        }


def model_dir(dataset_id: UUID) -> Path:
    return MODELS_DIR / str(dataset_id)


def manifest_path(dataset_id: UUID) -> Path:
    return dataset_export.manifest_path(dataset_id)


def _step(dataset_id: UUID, text: str) -> None:
    with _lock:
        _status.setdefault(str(dataset_id), {})["step"] = text


def _stretches(dataset_id: UUID, manifest: dict[str, Any], split: str) -> list[Stretch]:
    """The split's stretches with their labels and every camera's pose (each
    camera's pose is read and smoothed once per take)."""
    root = dataset_export.export_dir(dataset_id)  # the de-identified copy (ADR-014)
    takes = {t["take_id"]: t for t in manifest.get("takes", [])}
    cache: dict[
        str, tuple[list[tuple[float, Hand, str | None]], dict[str, Any], dict[str, Pose]]
    ] = {}
    out: list[Stretch] = []
    entries = manifest.get("splits", {}).get(split, [])
    for i, e in enumerate(entries):
        take = takes.get(e["take_id"])
        if take is None:
            continue
        if e["take_id"] not in cache:
            _step(dataset_id, f"reading {split} takes ({i + 1}/{len(entries)})")
            folder = root / take["folder"]
            raw = (
                json.loads((folder / take["labels"]["path"]).read_text())
                if take.get("labels")
                else []
            )
            labels = [
                (float(x["t_ms"]), x["hand"], x.get("punch_type"))
                for x in raw
                if x.get("hand") in ("left", "right")
            ]
            poses, tracks = {}, {}
            for rel in take.get("pose", []):
                if not (folder / rel).exists():
                    continue
                pose = read_pose(folder / rel)
                if len(pose.t) > 30:
                    cam = Path(rel).stem
                    poses[cam] = pose
                    tracks[cam] = punch_model.track_arrays(
                        pose.t, pose.wl[:, :, :3], pose.wl[:, :, 3]
                    )
            cache[e["take_id"]] = (labels, tracks, poses)
        labels, tracks, poses = cache[e["take_id"]]
        lo, hi = float(e["t_start_ms"]), float(e["t_end_ms"])
        out.append(
            Stretch(
                take_id=e["take_id"],
                block=str(e.get("block") or ""),
                t_start=lo,
                t_end=hi,
                labels=[(t, h) for t, h, _ in labels if lo <= t <= hi],
                typed=[(t, h, k) for t, h, k in labels if lo <= t <= hi and k in TYPES],
                stance=take.get("stance"),
                tracks=tracks,
                poses=poses,
            )
        )
    return out


def _pieces(lo: float, hi: float, gaps: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """[lo, hi] without the gaps."""
    out, at = [], lo
    for a, b in sorted(gaps):
        if a > at:
            out.append((at, min(a, hi)))
        at = max(at, b)
    if at < hi:
        out.append((at, hi))
    return [(a, b) for a, b in out if b - a >= SESSION_MIN_MS]


def _session_stretches(dataset_id: UUID) -> list[Stretch]:
    """Every cross-checked training session, per camera: from a couple of seconds
    before the wrists' first punch to after their last, cut where a wrist wasn't
    streaming, the punches on the camera's own clock (ADR-047)."""
    out: list[Stretch] = []
    found = session_corpus.sessions()
    for i, m in enumerate(found):
        _step(dataset_id, f"reading recorded sessions ({i + 1}/{len(found)})")
        for cam in m.cameras:
            pose = read_pose(cam.pose_path)
            if len(pose.t) <= 30:
                continue
            labels = [(cam.cam_t(t), h) for t, h in m.punches]
            typed = [(cam.cam_t(t), h, k) for t, h, k in m.typed]
            gaps = [(cam.cam_t(a), cam.cam_t(b)) for a, b in m.gaps]
            lo = max(min(t for t, _ in labels) - SESSION_MARGIN_MS, float(pose.t[0]))
            hi = min(max(t for t, _ in labels) + SESSION_MARGIN_MS, float(pose.t[-1]))
            track = punch_model.track_arrays(pose.t, pose.wl[:, :, :3], pose.wl[:, :, 3])
            for a, b in _pieces(lo, hi, gaps):
                out.append(
                    Stretch(
                        take_id=m.group,
                        block="session",
                        t_start=a,
                        t_end=b,
                        labels=[(t, h) for t, h in labels if a <= t <= b],
                        typed=[(t, h, k) for t, h, k in typed if a <= t <= b],
                        tracks={cam.device: track},
                        poses={cam.device: pose},
                    )
                )
    return out


def _rows(stretches: list[Stretch]) -> list[punch_model.Sample]:
    rows = []
    for s in stretches:
        for tr in s.tracks.values():
            r = punch_model.samples(tr, s.labels, s.t_start, s.t_end, group=s.take_id)
            if r is not None:
                rows.append(r)
    return rows


def _found(evs: list[tuple[float, Hand, float]], s: Stretch) -> list[DetectedPunch]:
    return [
        DetectedPunch(t_ms=t, hand=h, punch_type=None, confidence=p)
        for t, h, p in evs
        if s.t_start <= t <= s.t_end
    ]


def _pick_threshold(dataset_id: UUID, train: list[Stretch]) -> tuple[float, dict[str, Any]]:
    """The threshold with the best F1 on takes the model didn't see (grouped CV)."""
    takes = sorted({s.take_id for s in train})
    folds = [takes[i::3] for i in range(min(3, len(takes)))]
    tallies = {th: Tally() for th in THRESHOLDS}
    for k, held in enumerate(folds):
        _step(dataset_id, f"choosing the threshold (fold {k + 1}/{len(folds)})")
        fit_on = [s for s in train if s.take_id not in held]
        if not fit_on:
            continue
        model = punch_model.fit(_rows(fit_on), seed=k)
        for s in (s for s in train if s.take_id in held):
            for tr in s.tracks.values():
                probs = punch_model.probabilities(model, tr)
                for th in THRESHOLDS:
                    tallies[th].add(s.truth(), _found(punch_model.events(probs, th), s))
    best = max(THRESHOLDS, key=lambda th: (tallies[th].out()["f1"], -th))
    return best, tallies[best].out()


def _score_types(
    dataset_id: UUID,
    model: Any,
    s: Stretch,
    cam: str,
    tr: punch_model.Track,
    detected: list[DetectedPunch],
    types: dict[str, TypeTally],
    by_block: dict[str, TypeTally],
) -> None:
    """Name the stretch's typed punches on one camera — the classifier and the
    current rule-based namer, each given the true punch — and the counter's own
    punches that match a typed label (same hand, within TOLERANCE_MS)."""
    windows = punch_model.arm_windows(tr)
    truth = [(t, h) for t, h, _ in s.typed]
    named = punch_model.classify_types(model, tr, truth, s.stance, windows)
    for (t, h, label), mine in zip(s.typed, named, strict=True):
        history = s.poses[cam].frames(t - 400, t, dataset_id)
        theirs = classify_punch_type(history, h, s.stance) if len(history) >= 2 else None
        for tally in (types["model"], by_block["model"]):
            tally.add(label, mine)
        for tally in (types["baseline"], by_block["baseline"]):
            tally.add(label, theirs)
    found = [(d.t_ms, d.hand) for d in detected]
    found_named = punch_model.classify_types(model, tr, found, s.stance, windows)
    used: set[int] = set()
    for t, h, label in s.typed:
        best = min(
            (
                (abs(ft - t), k)
                for k, (ft, fh) in enumerate(found)
                if fh == h and k not in used and abs(ft - t) <= TOLERANCE_MS
            ),
            default=None,
        )
        if best is not None:
            used.add(best[1])
            types["end_to_end"].add(label, found_named[best[1]])


def _other_datasets(dataset_id: UUID) -> list[UUID]:
    """The other datasets with an export to learn from (ADR-059)."""
    out = []
    for m in sorted(dataset_store.DATASETS_DIR.glob("*/export/manifest.json")):
        try:
            other = UUID(m.parent.parent.name)
        except ValueError:
            continue
        if other != dataset_id:
            out.append(other)
    return out


def _others_stretches(dataset_id: UUID) -> tuple[list[Stretch], list[dict[str, Any]]]:
    """Every exported take of the other datasets — their train and test stretches
    alike — to learn from; this dataset's test takes stay the score (ADR-059)."""
    out: list[Stretch] = []
    used = []
    for other in _other_datasets(dataset_id):
        try:
            m = json.loads(manifest_path(other).read_text())
        except (OSError, ValueError):
            continue
        got = _stretches(other, m, "train") + _stretches(other, m, "test")
        if got:
            out += got
            used.append(
                {
                    "dataset_id": str(other),
                    "stretches": len(got),
                    "punches": sum(len(s.labels) for s in got),
                }
            )
    return out, used


def run(dataset_id: UUID, include_others: bool = True) -> dict[str, Any]:
    """Train and score; returns (and saves) the report. With `include_others`, the
    other exported datasets' takes join the training stretches (ADR-059)."""

    manifest = json.loads(manifest_path(dataset_id).read_text())
    train = _stretches(dataset_id, manifest, "train")
    test = _stretches(dataset_id, manifest, "test")
    if not train or not any(s.labels for s in train):
        raise ValueError("the export has no labelled training stretches")
    others, others_used = _others_stretches(dataset_id) if include_others else ([], [])
    train += others
    sessions = _session_stretches(dataset_id)  # for training only (ADR-047)
    train += sessions

    threshold, cv = _pick_threshold(dataset_id, train)
    _step(dataset_id, "training the model")
    model = punch_model.fit(_rows(train))

    type_model = None
    type_rows = [
        r
        for s in train
        for tr in s.tracks.values()
        if (r := punch_model.type_samples(tr, s.typed, s.t_start, s.t_end, group=s.take_id))
    ]
    if type_rows and len({c for r in type_rows for c in r.y.tolist()}) >= 2:
        _step(dataset_id, "training the punch-type classifier")
        type_model = punch_model.fit_types(type_rows)

    _step(dataset_id, "scoring it against the current counter")
    types = {"model": TypeTally(), "baseline": TypeTally(), "end_to_end": TypeTally()}
    types_by_block: dict[str, dict[str, TypeTally]] = defaultdict(
        lambda: {"model": TypeTally(), "baseline": TypeTally()}
    )
    overall = {"model": Tally(), "baseline": Tally()}
    by_block: dict[str, dict[str, Tally]] = defaultdict(
        lambda: {"model": Tally(), "baseline": Tally()}
    )
    by_camera: dict[str, dict[str, Tally]] = defaultdict(
        lambda: {"model": Tally(), "baseline": Tally()}
    )
    for s in test:
        for cam, tr in s.tracks.items():
            mine = _found(punch_model.events(punch_model.probabilities(model, tr), threshold), s)
            # the current counter, as the browser cameras run it (a second either
            # side so the block's first and last punches aren't cut off)
            frames = s.poses[cam].frames(s.t_start - 1000, s.t_end + 1000, dataset_id)
            base = [
                DetectedPunch(t_ms=e.t_ms, hand=e.hand, punch_type=None)
                for e in (camera_punches(frames) if len(frames) > 10 else [])
                if s.t_start <= e.t_ms <= s.t_end
            ]
            for name, found in (("model", mine), ("baseline", base)):
                overall[name].add(s.truth(), found)
                by_block[s.block][name].add(s.truth(), found)
                by_camera[cam][name].add(s.truth(), found)
            if type_model is not None and s.typed:
                _score_types(
                    dataset_id, type_model, s, cam, tr, mine, types, types_by_block[s.block]
                )

    out_dir = model_dir(dataset_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    version = 1 + max((int(p.stem[1:]) for p in out_dir.glob("v*.json")), default=0)
    model_file = out_dir / f"v{version}.joblib"
    model_files.dump(
        {
            "model": model,
            "threshold": threshold,
            "offsets": punch_model.OFFSETS,
            "hz": punch_model.HZ,
            # names each punch: straight / hook / uppercut → jab / cross by stance
            "type_model": type_model,
            "type_classes": punch_model.TYPE_CLASSES,
        },
        model_file,
    )
    report: dict[str, Any] = {
        "version": version,
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "dataset_id": str(dataset_id),
        "export_at": manifest.get("exported_at"),
        "split_strategy": manifest.get("split_strategy"),
        "model_file": str(model_file),
        "threshold": threshold,
        "data": {
            "takes": len(
                {s.take_id for s in train + test}
                - {s.take_id for s in sessions}
                - {s.take_id for s in others}
            ),
            "fighters": len({t["participant"] for t in manifest.get("takes", [])}),
            "train_stretches": len(train),
            "test_stretches": len(test),
            "train_punches": sum(len(s.labels) for s in train),
            "test_punches": sum(len(s.labels) for s in test),
            # the other datasets' takes, trained on and never scored (ADR-059)
            "other_datasets": others_used,
            # recorded training sessions, trained on and never scored (ADR-047)
            "sessions": len({s.take_id for s in sessions}),
            "session_stretches": len(sessions),
            "session_punches": sum(len(s.labels) for s in sessions),
            "reviewed_labels": all(
                (t.get("labels") or {}).get("reviewed") for t in manifest.get("takes", [])
            ),
        },
        "train_cv": cv,  # on takes held out while choosing the threshold
        "test": {name: t.out() for name, t in overall.items()},
        "by_block": [
            {"block": b, **{name: t.out() for name, t in v.items()}}
            for b, v in sorted(by_block.items())
        ],
        "by_camera": [
            {"camera": c, **{name: t.out() for name, t in v.items()}}
            for c, v in sorted(by_camera.items())
        ],
        "types": {
            "trained": type_model is not None,
            "train_punches": sum(len(s.typed) for s in train),
            "test_punches": sum(len(s.typed) for s in test),
            # given the true punch: the new classifier vs the current rule-based namer
            "test": {"model": types["model"].out(), "baseline": types["baseline"].out()},
            # the counter's own punches that match a label, named by the classifier
            "end_to_end": types["end_to_end"].out(),
            "by_block": [
                {"block": b, **{name: t.out() for name, t in v.items()}}
                for b, v in sorted(types_by_block.items())
            ],
        },
        "warnings": list(manifest.get("warnings") or []),
    }
    model_files.write_json(report, out_dir / f"v{version}.json")  # last: now it's in use
    log.info(
        "training.done",
        extra={
            "_ctx_dataset_id": str(dataset_id),
            "_ctx_version": version,
            "_ctx_f1_model": report["test"]["model"]["f1"],
            "_ctx_f1_baseline": report["test"]["baseline"]["f1"],
        },
    )
    return report


def start(dataset_id: UUID, include_others: bool = True) -> bool:
    """Train in the background; False if a run for this dataset is going already."""
    key = str(dataset_id)
    with _lock:
        if _status.get(key, {}).get("running"):
            return False
        _status[key] = {"running": True, "step": "starting", "error": None}
    if not BACKGROUND:
        return True

    def work() -> None:
        try:
            run(dataset_id, include_others)
            err = None
        except Exception as e:  # reported to the coach, not raised into a thread
            log.exception("training.failed", extra={"_ctx_dataset_id": key})
            err = str(e)[:300] or type(e).__name__
        with _lock:
            _status[key] = {"running": False, "step": None, "error": err}

    threading.Thread(target=work, daemon=True, name=f"train-{key[:8]}").start()
    return True


def status(dataset_id: UUID) -> dict[str, Any]:
    """{running, step, error, latest report, all runs}."""
    with _lock:
        st = dict(_status.get(str(dataset_id), {"running": False, "step": None, "error": None}))
    reports = []
    for p in sorted(model_dir(dataset_id).glob("v*.json"), key=lambda p: int(p.stem[1:])):
        try:
            reports.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    st["latest"] = reports[-1] if reports else None
    st["runs"] = [
        {
            "version": r["version"],
            "created_at": r["created_at"],
            "f1_model": r["test"]["model"]["f1"],
            "f1_baseline": r["test"]["baseline"]["f1"],
            "type_accuracy": ((r.get("types") or {}).get("test") or {})
            .get("model", {})
            .get("accuracy"),
        }
        for r in reports
    ]
    return st

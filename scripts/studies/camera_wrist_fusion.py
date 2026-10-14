"""Punch types from the cameras' 3D pose and the wrist sensors, combined — is the
pair better than either alone? (research branch research/camera-wrist-fusion)

Every typed punch of this project's completed dataset takes (read-only) gets:
- camera: the ADR-020 3D type model (analyze.punch_model) on each camera's pose,
  its class probabilities averaged over the cameras that saw the punch;
- wrist: the ADR-029 wrist type model (analyze.wrist_types) on that hand's window;
- combined: the two probability vectors averaged ("mean") or multiplied
  ("product"); a punch only one side saw keeps that side's answer.
5-fold cross-validation grouped by take: both models are trained on the other
takes each time, so every number is on takes they never saw. One participant.

Usage (from the checkout that holds data/):
    uv run python scripts/studies/camera_wrist_fusion.py [--out results.json]
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from analyze import punch_model
from analyze import wrist_types as wt
from api.services.wrist_type_model import _imu_streams
from capture.cv.writer import read_pose_parquet

DATASETS = Path("data/datasets")
MOTIONS = list(wt.MOTIONS)  # straight, hook, uppercut


@dataclass
class Punch:
    take: str
    t_ms: float
    hand: str
    motion: str
    wrist: np.ndarray | None = None
    cams: list[np.ndarray] = field(default_factory=list)


def load() -> list[Punch]:
    out: list[Punch] = []
    for tj in sorted(DATASETS.glob("*/takes/*/take.json")):
        folder = tj.parent
        take = json.loads(tj.read_text())
        labels_file = folder / "labels.json"
        if take.get("status") != "completed" or not labels_file.exists():
            continue
        typed = [
            lab
            for lab in json.loads(labels_file.read_text())
            if lab.get("punch_type") in wt.TYPE_TO_MOTION
        ]
        if not typed:
            continue
        punches = [
            Punch(
                take["take_id"],
                float(lab["t_ms"]),
                lab["hand"],
                wt.TYPE_TO_MOTION[lab["punch_type"]],
            )
            for lab in typed
        ]
        if (folder / "imu.csv").exists():
            streams = _imu_streams(folder)
            for p in punches:
                t, imu = streams[p.hand]
                win = wt.window(t, imu, p.t_ms) if len(t) else None
                p.wrist = wt.features(win, p.hand) if win is not None else None
        for cam in sorted((folder / "pose").glob("*.parquet")):
            frames = read_pose_parquet(cam)
            if len(frames) < 10:
                continue
            tr = punch_model.track(frames)
            win = punch_model.arm_windows(tr)
            for p in punches:
                i = punch_model._frame(tr, p.t_ms)
                if i is not None:
                    p.cams.append(win[p.hand][i])
        out += punches
    return out


def proba(model: Any, x: np.ndarray) -> np.ndarray:
    """Class probabilities in MOTIONS order (a class the fold never saw gets 0)."""
    p = model.predict_proba(x)
    cols = [list(model.classes_).index(m) if m in model.classes_ else None for m in MOTIONS]
    return np.stack([p[:, c] if c is not None else np.zeros(len(x)) for c in cols], axis=1)


def report(name: str, y: list[str], pred: list[str]) -> dict[str, Any]:
    ya, pa = np.array(y), np.array(pred)
    acc = float(np.mean(ya == pa))
    rec = {m: round(float(np.mean(pa[ya == m] == m)), 3) for m in MOTIONS if np.any(ya == m)}
    print(f"{name:44} {acc:6.1%}  of {len(ya):4}   recall {rec}")
    return {"accuracy": round(acc, 3), "n": len(ya), "recall": rec}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    from sklearn.model_selection import GroupKFold

    punches = load()
    takes = np.array([p.take for p in punches])
    print(
        f"{len(punches)} typed punches, {len(set(takes.tolist()))} takes; "
        f"{sum(p.wrist is not None for p in punches)} with a wrist window, "
        f"{sum(bool(p.cams) for p in punches)} seen by a camera "
        f"({sum(len(p.cams) for p in punches)} camera views)\n"
    )
    res: dict[str, dict[str, list[str]]] = {
        k: {"y": [], "pred": []}
        for k in (
            "camera_view",
            "one_view_wrist_mean",
            "one_view_wrist_product",
            "camera",
            "wrist",
            "mean",
            "product",
            "both_seen_camera",
            "both_seen_wrist",
            "both_seen_mean",
        )
    }

    def add(k: str, y: str, pred: str) -> None:
        res[k]["y"].append(y)
        res[k]["pred"].append(pred)

    for tr, te in GroupKFold(n_splits=5).split(
        np.zeros(len(punches)), np.zeros(len(punches)), takes
    ):
        train = [punches[i] for i in tr]
        rows = [
            punch_model.TypeSample(
                x=np.stack(p.cams), y=np.array([p.motion] * len(p.cams)), group=p.take
            )
            for p in train
            if p.cams
        ]
        cam_model = punch_model.fit_types(rows)
        wx = np.array([p.wrist for p in train if p.wrist is not None])
        wy = np.array([p.motion for p in train if p.wrist is not None])
        wrist_model = wt.fit(wx, wy)
        for i in te:
            p = punches[i]
            pc = proba(cam_model, np.stack(p.cams)) if p.cams else None
            pw = proba(wrist_model, p.wrist[None, :])[0] if p.wrist is not None else None
            if pc is not None:
                for row in pc:
                    add("camera_view", p.motion, MOTIONS[int(np.argmax(row))])
                    if pw is not None:  # a single phone with the wrists
                        add(
                            "one_view_wrist_mean", p.motion, MOTIONS[int(np.argmax((row + pw) / 2))]
                        )
                        add(
                            "one_view_wrist_product",
                            p.motion,
                            MOTIONS[int(np.argmax(row * pw + 1e-9))],
                        )
                add("camera", p.motion, MOTIONS[int(np.argmax(pc.mean(axis=0)))])
            if pw is not None:
                add("wrist", p.motion, MOTIONS[int(np.argmax(pw))])
            if pc is not None and pw is not None:
                c = pc.mean(axis=0)
                add("mean", p.motion, MOTIONS[int(np.argmax((c + pw) / 2))])
                add("product", p.motion, MOTIONS[int(np.argmax(c * pw + 1e-9))])
                add("both_seen_camera", p.motion, MOTIONS[int(np.argmax(c))])
                add("both_seen_wrist", p.motion, MOTIONS[int(np.argmax(pw))])
                add("both_seen_mean", p.motion, MOTIONS[int(np.argmax((c + pw) / 2))])
            elif pc is not None or pw is not None:  # only one side saw it
                only = pc.mean(axis=0) if pc is not None else pw
                add("mean", p.motion, MOTIONS[int(np.argmax(only))])
                add("product", p.motion, MOTIONS[int(np.argmax(only))])

    names = {
        "camera_view": "camera, one view at a time",
        "one_view_wrist_mean": "one camera + wrist (mean)",
        "one_view_wrist_product": "one camera + wrist (product)",
        "camera": "camera, 3 views averaged",
        "wrist": "wrist",
        "mean": "combined (mean of probabilities)",
        "product": "combined (product of probabilities)",
        "both_seen_camera": "  — punches both saw: camera",
        "both_seen_wrist": "  — punches both saw: wrist",
        "both_seen_mean": "  — punches both saw: combined (mean)",
    }
    out = {k: report(names[k], v["y"], v["pred"]) for k, v in res.items() if v["y"]}
    if args.out:
        args.out.write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()

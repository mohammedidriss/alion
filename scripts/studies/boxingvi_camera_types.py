"""Can a camera punch-type model learned from BoxingVI's 2D pose name this
project's punches — and beat the camera models it has now? (research branch)

Data (read-only):
- BoxingVI (Kumar et al., arXiv:2511.16524): data/external/boxingvi — the released
  2D pose (COCO-17, one clip per punch) and labels for V1–V10, no video; 18
  YouTube athletes. No licence stated: evaluation only.
- This project's dataset takes: every completed take's typed labels (t_ms, hand,
  jab|cross|hook|uppercut — from the protocol blocks, timed by the wrist sensors)
  and each camera's MediaPipe pose.

Scored on this project's punches (motion: straight / hook / uppercut), every
camera view counted:
- rule      the live rule the camera box uses now (analyze.punch_type_heuristic)
- adr020    the 3D camera type model (analyze.punch_model), trained on this
            project's takes, 5-fold grouped by take
- bvi2d     a 2D model trained on BoxingVI only (other people, YouTube views)
- both2d    BoxingVI + this project's 2D, 5-fold grouped by take
And, as a check of the 2D features themselves: BoxingVI on itself, grouped by video.

Usage (from the checkout that holds data/):
    uv run python scripts/studies/boxingvi_camera_types.py [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from analyze import pose2d_types as p2
from analyze import punch_model
from analyze.punch_type_heuristic import classify_punch_type
from capture.cv.writer import read_pose_parquet

BVI = Path("data/external/boxingvi")
DATASETS = Path("data/datasets")
BEFORE_MS, AFTER_MS = 300.0, 250.0  # our punch label sits near full extension
TYPE_TO_MOTION = {"jab": "straight", "cross": "straight", "hook": "hook", "uppercut": "uppercut"}
_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _xlsx_rows(path: Path) -> list[list[str]]:
    """A sheet's rows as strings, read straight from the xlsx (no extra package)."""
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(t.text or "" for t in si.iter(f"{{{_NS['m']}}}t")))
    sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
    rows = []
    for r in sheet.find("m:sheetData", _NS).findall("m:row", _NS):  # type: ignore[union-attr]
        vals = []
        for c in r.findall("m:c", _NS):
            v = c.find("m:v", _NS)
            val = v.text if v is not None else None
            if c.get("t") == "s" and val is not None:
                val = shared[int(val)]
            vals.append(val or "")
        rows.append(vals)
    return rows


def boxingvi(mirror: bool = True) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """BoxingVI rows (each clip, and its mirror image), motions, video ids."""
    xs, ys, groups = [], [], []
    for n in range(1, 11):
        clips = np.load(BVI / "Skeleton_data" / f"V{n}.npy")
        labels = []
        for row in _xlsx_rows(BVI / "Annotation_files" / f"V{n}.xlsx"):
            kind = next(
                (
                    p2.BOXINGVI_CLASS[c.strip().lower()]
                    for c in row
                    if c.strip().lower() in p2.BOXINGVI_CLASS
                ),
                None,
            )
            if kind:
                labels.append(kind)
        if len(labels) != len(clips):
            print(
                f"  V{n}: {len(clips)} clips vs {len(labels)} labels — matched in order, extras dropped"
            )
        for clip, motion in zip(clips, labels, strict=False):
            real = clip[np.abs(clip).sum(axis=(1, 2)) > 0]  # drop the zero padding
            for m in (False, True) if mirror else (False,):
                row = p2.features(real, mirror=m)
                if row is not None:
                    xs.append(row)
                    ys.append(motion)
                    groups.append(f"V{n}")
    return np.array(xs), np.array(ys), np.array(groups)


def ours() -> dict[str, Any]:
    """Every camera view of every typed punch in this project's takes."""
    out: dict[str, list[Any]] = {k: [] for k in ("x", "y", "take", "camera", "rule", "key")}
    adr_rows = []
    for tj in sorted(DATASETS.glob("*/takes/*/take.json")):
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
        stance = take.get("stance")
        for cam in sorted((folder / "pose").glob("*.parquet")):
            frames = read_pose_parquet(cam)
            if len(frames) < 10:
                continue
            t = np.array([f.t_ms for f in frames])
            img = np.array([[[lm.x, lm.y] for lm in f.landmarks] for f in frames])
            coco = p2.from_mediapipe(img)
            for lab in typed:
                at = float(lab["t_ms"])
                sel = (t >= at - BEFORE_MS) & (t <= at + AFTER_MS)
                row = p2.features(coco[sel]) if sel.sum() >= 4 else None
                if row is None:
                    continue
                i = int(np.searchsorted(t, at))
                history = frames[max(0, i - 5) : i + 1]
                rule = classify_punch_type(history, lab["hand"], stance) if history else None
                out["x"].append(row)
                out["y"].append(TYPE_TO_MOTION[lab["punch_type"]])
                out["take"].append(take["take_id"])
                out["camera"].append(cam.stem)
                out["rule"].append(TYPE_TO_MOTION.get(str(rule), "none") if rule else "none")
                out["key"].append((take["take_id"], round(at, 1), lab["hand"]))
            tr = punch_model.track(frames)
            pts = [(float(lab["t_ms"]), lab["hand"], lab["punch_type"]) for lab in typed]
            s = punch_model.type_samples(tr, pts, 0.0, float("inf"), group=take["take_id"])
            if s is not None:
                adr_rows.append(s)
    res = {k: np.array(v) if k != "key" else v for k, v in out.items()}
    res["adr_rows"] = adr_rows
    return res


def score(name: str, y: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    acc = float(np.mean(y == pred))
    rec = {c: round(float(np.mean(pred[y == c] == c)), 3) for c in p2.MOTIONS if np.any(y == c)}
    print(f"{name:42} {acc:6.1%}   recall {rec}")
    return {"accuracy": round(acc, 3), "recall": rec, "n": len(y)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.model_selection import GroupKFold

    def fit(x: np.ndarray, y: np.ndarray) -> Any:
        m = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.08, random_state=0, class_weight="balanced"
        )
        return m.fit(x, y)

    bx, by, bg = boxingvi()
    print(
        f"BoxingVI: {len(by) // 2} clips (×2 mirrored) from {len(set(bg.tolist()))} videos: {dict(Counter(by[::2].tolist()))}"
    )
    o = ours()
    oy = o["y"]
    print(
        f"this project: {len(oy)} camera views of {len(set(o['key']))} punches, {len(set(o['take'].tolist()))} takes\n"
    )
    results: dict[str, Any] = {}

    pred = np.empty_like(by)
    for tr, te in GroupKFold(n_splits=5).split(bx, by, bg):
        pred[te] = fit(bx[tr], by[tr]).predict(bx[te])
    results["bvi_on_bvi"] = score("BoxingVI on BoxingVI (videos held out)", by, pred)

    results["rule"] = score("live rule (now)", oy, o["rule"])

    rows = o["adr_rows"]
    groups = np.array([r.group for r in rows])
    adr_y, adr_pred = [], []
    for tr, te in GroupKFold(n_splits=5).split(np.zeros(len(rows)), np.zeros(len(rows)), groups):
        model = punch_model.fit_types([rows[i] for i in tr])
        for i in te:
            adr_y += rows[i].y.tolist()
            adr_pred += model.predict(rows[i].x).tolist()
    results["adr020"] = score(
        "ADR-020 3D model (your takes held out)", np.array(adr_y), np.array(adr_pred)
    )

    bvi_model = fit(bx, by)
    results["bvi2d"] = score("BoxingVI 2D model (other people only)", oy, bvi_model.predict(o["x"]))

    pred = np.empty_like(oy)
    for tr, te in GroupKFold(n_splits=5).split(o["x"], oy, o["take"]):
        pred[te] = fit(np.vstack([bx, o["x"][tr]]), np.concatenate([by, oy[tr]])).predict(
            o["x"][te]
        )
    results["both2d"] = score("BoxingVI + your 2D (your takes held out)", oy, pred)
    own = np.empty_like(oy)
    for tr, te in GroupKFold(n_splits=5).split(o["x"], oy, o["take"]):
        own[te] = fit(o["x"][tr], oy[tr]).predict(o["x"][te])
    results["own2d"] = score("your 2D only (your takes held out)", oy, own)

    print("\nby camera (BoxingVI 2D model):")
    bp = bvi_model.predict(o["x"])
    for cam in sorted(set(o["camera"].tolist())):
        sel = o["camera"] == cam
        print(f"  {cam:20} {np.mean(bp[sel] == oy[sel]):6.1%}  ({sel.sum()} views)")
    if args.out:
        args.out.write_text(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

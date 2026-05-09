"""Public-dataset ETL — boxing clips → MediaPipe keypoint windows.

Produces the training set for the LSTM second-pass classifier.

Sources we currently support:
  - UCF101: classes `BoxingPunchingBag`, `BoxingSpeedBag`
  - HMDB-51: class `punch`

Both are clip-level labels — each video file gets one label. We extract
MediaPipe Pose on every frame, pack into fixed-length sliding windows,
and emit `data/ml/datasets/punch_windows.parquet` with columns:

    window_id, source, label, t_start_ms,
    lm00_x, lm00_y, lm00_z, lm00_v,  # × 33 landmarks
    wl00_x, wl00_y, wl00_z, wl00_v,  # × 33 world landmarks
    ... × WINDOW_FRAMES rows packed as a flat 1-D feature vector

Layout: each row is one window; columns are
    f0_lm00_x, f0_lm00_y, ..., f0_wl32_v,
    f1_lm00_x, ...,
    ... up to f<WINDOW_FRAMES-1>_...

Run:
    # First, place the source files on disk:
    #   data/ml/raw/ucf101/videos/<class>/<file>.avi
    #   data/ml/raw/hmdb51/videos/<class>/<file>.avi
    # Or pass --downloads-already-extracted=path
    uv run python -m scripts.ml.prep_public_dataset \
        --ucf101 data/ml/raw/ucf101/videos \
        --hmdb51 data/ml/raw/hmdb51/videos \
        --out data/ml/datasets/punch_windows.parquet

The downloads themselves are large (UCF101 ~6.5 GB, HMDB-51 ~2 GB) and
require accepting their respective licences, so this script does NOT
fetch them. See README in `data/ml/raw/` for instructions.
"""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

WINDOW_FRAMES = 30  # ~1 s at 30 fps
STRIDE_FRAMES = 10  # 33% overlap

UCF101_CLASSES_PUNCH = {"BoxingPunchingBag", "BoxingSpeedBag", "Punch"}
HMDB51_CLASSES_PUNCH = {"punch", "boxing"}


def _iter_video_files(root: Path, classes: set[str]) -> Iterator[tuple[str, Path]]:
    """Yield (class_name, video_path) for class-named subfolders."""
    if not root.exists():
        return
    for class_dir in sorted(root.iterdir()):
        if not class_dir.is_dir():
            continue
        if class_dir.name not in classes:
            continue
        for video in sorted(class_dir.iterdir()):
            if video.suffix.lower() in (".avi", ".mp4", ".mov", ".mkv"):
                yield class_dir.name, video


def _extract_pose_sequence(video_path: Path) -> list[list[float]]:
    """Run MediaPipe Pose over every frame; return list of flat feature
    vectors. Each frame contributes 33 landmarks × 4 fields (x,y,z,v) +
    33 world landmarks × 4 = 264 features per frame.
    """
    import cv2
    import mediapipe as mp

    mp_pose = mp.solutions.pose
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    out: list[list[float]] = []
    with mp_pose.Pose(model_complexity=1, enable_segmentation=False) as pose:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = pose.process(rgb)
            if not res.pose_landmarks or not res.pose_world_landmarks:
                # Fill missing frame with zeros so window indexing stays
                # aligned. The training script can mask zero-rows.
                out.append([0.0] * (33 * 4 * 2))
                continue
            row: list[float] = []
            for lm in res.pose_landmarks.landmark:
                row.extend([lm.x, lm.y, lm.z, lm.visibility])
            for wl in res.pose_world_landmarks.landmark:
                row.extend([wl.x, wl.y, wl.z, wl.visibility])
            out.append(row)
    cap.release()
    return out


def _windowize(seq: list[list[float]], window: int, stride: int) -> list[list[float]]:
    out: list[list[float]] = []
    for start in range(0, max(0, len(seq) - window + 1), stride):
        flat: list[float] = []
        for i in range(start, start + window):
            flat.extend(seq[i])
        out.append(flat)
    return out


def _label_for(class_name: str, source: str) -> str:
    """Coarse binary label for now — 'punch' if the clip is from a
    punch class, else 'other'. Refine to per-type later when ground-
    truth event timestamps are available.
    """
    if source == "ucf101":
        return "punch" if class_name in UCF101_CLASSES_PUNCH else "other"
    if source == "hmdb51":
        return "punch" if class_name in HMDB51_CLASSES_PUNCH else "other"
    return "other"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ucf101", type=Path, default=None, help="UCF101 videos root")
    ap.add_argument("--hmdb51", type=Path, default=None, help="HMDB-51 videos root")
    ap.add_argument(
        "--negatives",
        type=Path,
        default=None,
        help=(
            "Optional folder of non-punch videos for negative samples. "
            "Subfolders treated as class names (any name ≠ punch class)."
        ),
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("data/ml/datasets/punch_windows.parquet"),
    )
    ap.add_argument("--window", type=int, default=WINDOW_FRAMES)
    ap.add_argument("--stride", type=int, default=STRIDE_FRAMES)
    args = ap.parse_args()

    args.out.parent.mkdir(parents=True, exist_ok=True)

    n_features_per_frame = 33 * 4 * 2  # 264
    columns: dict[str, list] = {
        "window_id": [],
        "source": [],
        "label": [],
        "video_name": [],
    }
    feat_cols = [f"f{i}_x" for i in range(args.window * n_features_per_frame)]
    for c in feat_cols:
        columns[c] = []

    sources: list[tuple[str, Path | None, set[str]]] = [
        ("ucf101", args.ucf101, UCF101_CLASSES_PUNCH),
        ("hmdb51", args.hmdb51, HMDB51_CLASSES_PUNCH),
    ]
    if args.negatives is not None:
        # Treat every subfolder as a "non-punch" example.
        sources.append(("negatives", args.negatives, set()))

    next_window_id = 0
    for source_name, root, _classes in sources:
        if root is None:
            print(f"  ↳ skipping {source_name} (no root provided)")
            continue
        videos: list[tuple[str, Path]] = []
        if source_name == "negatives":
            for class_dir in sorted(root.iterdir()) if root.exists() else []:
                if not class_dir.is_dir():
                    continue
                for v in sorted(class_dir.iterdir()):
                    if v.suffix.lower() in (".avi", ".mp4", ".mov", ".mkv"):
                        videos.append((class_dir.name, v))
        else:
            videos = list(_iter_video_files(root, _classes))
        print(f"  {source_name}: {len(videos)} clips")
        for class_name, video in videos:
            seq = _extract_pose_sequence(video)
            if len(seq) < args.window:
                continue
            label = "other" if source_name == "negatives" else _label_for(class_name, source_name)
            wins = _windowize(seq, args.window, args.stride)
            for w in wins:
                columns["window_id"].append(next_window_id)
                columns["source"].append(source_name)
                columns["label"].append(label)
                columns["video_name"].append(video.name)
                for i, val in enumerate(w):
                    columns[f"f{i}_x"].append(val)
                next_window_id += 1
            print(f"    {video.name} → {len(wins)} windows ({label})")

    if next_window_id == 0:
        print("no windows produced — check the input paths.")
        return

    table = pa.table(columns)
    pq.write_table(table, args.out)
    print(f"\nwrote {next_window_id} windows ({args.window} frames each) to {args.out}")
    print(f"feature dim per window: {args.window * n_features_per_frame}")
    label_counts: dict[str, int] = {}
    for label in columns["label"]:
        label_counts[label] = label_counts.get(label, 0) + 1
    print("label distribution:", label_counts)
    np.set_printoptions(suppress=True)


if __name__ == "__main__":
    main()

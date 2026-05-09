"""ETL — Olympic Boxing Punch Classification Video Dataset → keypoint windows.

Source layout (one folder per match):
    Datasets/Olympic Boxing Punch Classification Video Dataset/
    └── task_<id>/
        ├── annotations.json    # CVAT export
        └── data/
            └── <name>.mp4

Annotation schema (CVAT):
    [{"tracks": [{"label": "...", "shapes": [{"frame": N, "outside": bool, ...}, ...]}, ...]}]

Each `track` is one labelled punch event. Its active span runs from
`min(frame where outside=false)` to `max(frame where outside=false)`,
i.e. the frames during which the punch is mid-trajectory. Eight Polish
labels translate to {block,miss,head,body}_{L,R}.

Output: `data/ml/datasets/olympic_punch_windows.parquet` with columns
matching the trainer's expected schema:

    window_id, source, label, video_name,
    f0_x, f1_x, ..., f<window*264 - 1>_x

Binary `label` ∈ {"punch", "other"}: a window is "punch" iff its
**center frame** falls inside any annotated track's active span.
Multi-class hand/target labels are kept too (`hand_label`,
`target_label`) for downstream finetuning, but the trainer that ships
with the project reads `label`.

Run:
    uv run python -m scripts.ml.prep_olympic_boxing \
        --root "Datasets/Olympic Boxing Punch Classification Video Dataset" \
        --out data/ml/datasets/olympic_punch_windows.parquet \
        --frame-stride 2
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

WINDOW_FRAMES = 30
STRIDE_FRAMES = 10
N_FEATURES_PER_FRAME = 33 * 4 * 2  # 33 lm + 33 wl, each (x, y, z, v)

# Polish → English schema. Hand is parsed from the suffix.
POLISH_TO_TARGET = {
    "Blok": "block",
    "Chybienie": "miss",
    "Głowa": "head",
    "Korpus": "body",
}


def _parse_cvat_intervals(
    path: Path,
) -> list[tuple[int, int, str, str]]:
    """Returns (start_frame, end_frame_inclusive, target, hand) per track."""
    with path.open() as f:
        data = json.load(f)
    if isinstance(data, list):
        data = data[0]
    intervals: list[tuple[int, int, str, str]] = []
    for tr in data.get("tracks", []):
        shapes = tr.get("shapes", [])
        active = [s for s in shapes if not s.get("outside", False)]
        if not active:
            continue
        start = min(int(s["frame"]) for s in active)
        end = max(int(s["frame"]) for s in active)
        label = tr.get("label", "")
        head = label.split(" ", 1)[0] if label else ""
        target = POLISH_TO_TARGET.get(head, "punch")
        hand = "left" if "lewą" in label else "right" if "prawą" in label else "unknown"
        intervals.append((start, end, target, hand))
    return intervals


def _stream_pose_features(video_path: Path, frame_stride: int) -> dict[int, list[float]]:
    """Decode → MediaPipe Tasks PoseLandmarker → feature vector,
    frame-by-frame (streaming).

    Uses the same PoseLandmarker the live capture pipeline uses
    (`packages/capture/cv/pose.py`) — the legacy `mp.solutions.pose`
    API isn't shipped in the lightweight mediapipe wheel installed
    here. Returns {frame_index: feature_vec_264}.
    """
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    from capture.cv.pose import ensure_pose_model

    out: dict[int, list[float]] = {}
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return out
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(ensure_pose_model())),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.PoseLandmarker.create_from_options(options)
    try:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % frame_stride != 0:
                i += 1
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            t_ms_int = int((i / fps) * 1000.0)
            res = landmarker.detect_for_video(mp_image, t_ms_int)
            if not res.pose_landmarks or len(res.pose_landmarks[0]) != 33:
                out[i] = [0.0] * N_FEATURES_PER_FRAME
                i += 1
                continue
            row: list[float] = []
            for lm in res.pose_landmarks[0]:
                row.extend(
                    [lm.x, lm.y, lm.z, max(0.0, min(1.0, getattr(lm, "visibility", 1.0) or 0.0))]
                )
            wl = getattr(res, "pose_world_landmarks", None)
            if wl and len(wl) > 0 and len(wl[0]) == 33:
                for lm in wl[0]:
                    row.extend(
                        [
                            lm.x,
                            lm.y,
                            lm.z,
                            max(0.0, min(1.0, getattr(lm, "visibility", 1.0) or 0.0)),
                        ]
                    )
            else:
                row.extend([0.0] * (33 * 4))
            out[i] = row
            i += 1
    finally:
        landmarker.close()
        cap.release()
    return out


def _label_for_window(
    center_frame: int, intervals: list[tuple[int, int, str, str]]
) -> tuple[str, str, str]:
    """Returns (binary_label, hand_label, target_label)."""
    for start, end, target, hand in intervals:
        if start <= center_frame <= end:
            return ("punch", hand, target)
    return ("other", "none", "none")


def _windows_from_clip(
    feats: dict[int, list[float]],
    intervals: list[tuple[int, int, str, str]],
    *,
    window: int,
    stride: int,
) -> list[tuple[int, list[float], str, str, str]]:
    """Slide windows over feature-bearing frames; return labelled windows.

    Each window covers `window` *consecutive feature frames* (after
    stride sub-sampling). The window's label uses the original-frame
    index of the center feature frame so the labels remain aligned to
    the source annotations.
    """
    feat_indices = sorted(feats.keys())
    if len(feat_indices) < window:
        return []
    out: list[tuple[int, list[float], str, str, str]] = []
    for start in range(0, len(feat_indices) - window + 1, stride):
        idx_window = feat_indices[start : start + window]
        flat: list[float] = []
        for idx in idx_window:
            flat.extend(feats[idx])
        center_orig = idx_window[window // 2]
        binary, hand, target = _label_for_window(center_orig, intervals)
        out.append((center_orig, flat, binary, hand, target))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="dataset root folder")
    ap.add_argument(
        "--out",
        type=Path,
        default=Path("data/ml/datasets/olympic_punch_windows.parquet"),
    )
    ap.add_argument("--window", type=int, default=WINDOW_FRAMES)
    ap.add_argument("--stride", type=int, default=STRIDE_FRAMES)
    ap.add_argument(
        "--frame-stride",
        type=int,
        default=2,
        help="Process every Nth frame from the source video (default 2).",
    )
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    if not args.root.exists():
        raise SystemExit(f"dataset root not found: {args.root}")

    feat_cols = [f"f{i}_x" for i in range(args.window * N_FEATURES_PER_FRAME)]
    columns: dict[str, list] = {
        "window_id": [],
        "source": [],
        "video_name": [],
        "label": [],
        "hand_label": [],
        "target_label": [],
        "center_frame": [],
    }
    for c in feat_cols:
        columns[c] = []

    next_window_id = 0
    n_punch = 0
    n_other = 0

    # Resume support: each clip writes a sidecar parquet first, then we
    # concat at the end. Lets us re-run after a crash without redoing
    # MediaPipe over the already-processed clips.
    sidecar_dir = args.out.parent / (args.out.stem + "_sidecars")
    sidecar_dir.mkdir(parents=True, exist_ok=True)

    task_dirs = sorted(d for d in args.root.iterdir() if d.is_dir())
    print(f"found {len(task_dirs)} task folders")

    for task_dir in task_dirs:
        annot = task_dir / "annotations.json"
        mp4 = next((p for p in task_dir.rglob("*.mp4")), None)
        if not annot.exists() or mp4 is None:
            print(f"  skip {task_dir.name} (missing annotation or video)")
            continue
        sidecar = sidecar_dir / f"{task_dir.name}.parquet"
        if sidecar.exists():
            print(f"  resume {task_dir.name}: sidecar already present, skipping extraction")
            continue
        try:
            intervals = _parse_cvat_intervals(annot)
        except Exception as e:
            print(f"  skip {task_dir.name}: bad annotations ({e})")
            continue
        print(f"  {task_dir.name}: {mp4.name}  ·  {len(intervals)} tracks")

        feats = _stream_pose_features(mp4, args.frame_stride)
        if not feats:
            print("    failed to open video")
            continue
        print(f"    extracted pose for {len(feats)} frames (stride={args.frame_stride})")

        windows = _windows_from_clip(feats, intervals, window=args.window, stride=args.stride)
        n_p_clip = sum(1 for _, _, b, _, _ in windows if b == "punch")
        n_o_clip = len(windows) - n_p_clip
        n_punch += n_p_clip
        n_other += n_o_clip
        print(f"    → {len(windows)} windows  (punch={n_p_clip}, other={n_o_clip})")

        # Build a sidecar parquet for this clip, then concat at the end.
        sidecar_cols: dict[str, list] = {k: [] for k in columns}
        for center_frame, flat, binary, hand, target in windows:
            sidecar_cols["window_id"].append(-1)  # final ids assigned at concat
            sidecar_cols["source"].append("olympic_boxing")
            sidecar_cols["video_name"].append(mp4.name)
            sidecar_cols["label"].append(binary)
            sidecar_cols["hand_label"].append(hand)
            sidecar_cols["target_label"].append(target)
            sidecar_cols["center_frame"].append(center_frame)
            for i, val in enumerate(flat):
                sidecar_cols[f"f{i}_x"].append(val)
        pq.write_table(pa.table(sidecar_cols), sidecar)

    # Concat all sidecars (whether produced just now or carried over
    # from a previous interrupted run) into the final parquet.
    sidecar_files = sorted(sidecar_dir.glob("*.parquet"))
    if not sidecar_files:
        print("no sidecars produced — check the dataset path.")
        return
    print(f"\nconcatenating {len(sidecar_files)} sidecars …")
    tables = [pq.read_table(f) for f in sidecar_files]
    full = pa.concat_tables(tables)
    # Re-assign window_id to a contiguous sequence.
    full = full.set_column(
        full.column_names.index("window_id"),
        "window_id",
        pa.array(list(range(full.num_rows)), type=pa.int64()),
    )
    pq.write_table(full, args.out)
    next_window_id = full.num_rows
    label_arr = full.column("label").to_pylist()
    n_punch = sum(1 for v in label_arr if v == "punch")
    n_other = sum(1 for v in label_arr if v == "other")
    print(f"\nwrote {next_window_id} windows to {args.out}")
    print(f"label distribution: punch={n_punch} other={n_other}")
    np.set_printoptions(suppress=True)


if __name__ == "__main__":
    main()

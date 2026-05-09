"""Relabel the Olympic Boxing windows parquet with an overlap-fraction rule.

Original labelling (`prep_olympic_boxing.py`) marks a window "punch"
iff its center frame falls inside any annotated track. With 30-frame
windows (~1.2 s) and 10-frame tracks (~0.4 s), most "punch" windows
are 60 % non-punch context, and many "other" windows still contain a
partial punch — labels are noisy at boundaries.

This script reuses the already-extracted MediaPipe features in the
parquet (no re-extraction needed) and re-derives labels using:

    label = "punch"  iff  overlap_fraction >= threshold

where overlap_fraction is the fraction of the window's source-frame
span that falls inside *any* annotated track. Default threshold 0.3
catches windows where ~⅓ of the time is punch — cleaner positives, more
positives.

Run:
    uv run python -m scripts.ml.relabel_olympic \
        --in data/ml/datasets/olympic_punch_windows.parquet \
        --root "Datasets/Olympic Boxing Punch Classification Video Dataset" \
        --threshold 0.3 \
        --out data/ml/datasets/olympic_punch_windows_v2.parquet
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Must match prep_olympic_boxing.py constants.
WINDOW_FRAMES = 30
FRAME_STRIDE = 2  # only used to derive the source-frame span; default
SOURCE_FRAMES_PER_WINDOW = WINDOW_FRAMES * FRAME_STRIDE  # 60


def _intervals_for_video(annot_path: Path) -> list[tuple[int, int]]:
    """Return (start_frame, end_frame_inclusive) for every active track.

    Drops the label/hand metadata — relabelling is binary (any punch
    type counts as "punch").
    """
    with annot_path.open() as f:
        data = json.load(f)
    if isinstance(data, list):
        data = data[0]
    intervals: list[tuple[int, int]] = []
    for tr in data.get("tracks", []):
        active = [s for s in tr.get("shapes", []) if not s.get("outside", False)]
        if not active:
            continue
        intervals.append(
            (
                min(int(s["frame"]) for s in active),
                max(int(s["frame"]) for s in active),
            )
        )
    return intervals


def _build_video_index(root: Path) -> dict[str, list[tuple[int, int]]]:
    """Walk the dataset root; map each .mp4 filename → list of intervals."""
    index: dict[str, list[tuple[int, int]]] = {}
    for task in sorted(d for d in root.iterdir() if d.is_dir()):
        annot = task / "annotations.json"
        mp4 = next((p for p in task.rglob("*.mp4")), None)
        if not annot.exists() or mp4 is None:
            continue
        try:
            index[mp4.name] = _intervals_for_video(annot)
        except Exception:
            continue
    return index


def _overlap_fraction(
    center_frame: int, intervals: list[tuple[int, int]]
) -> float:
    """Fraction of the window's source-frame span inside any track."""
    half = SOURCE_FRAMES_PER_WINDOW // 2
    win_start = center_frame - half
    win_end = center_frame + half - 1  # inclusive
    overlap = 0
    for s, e in intervals:
        lo = max(win_start, s)
        hi = min(win_end, e)
        if hi >= lo:
            overlap += hi - lo + 1
    return overlap / SOURCE_FRAMES_PER_WINDOW


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", type=Path, required=True)
    ap.add_argument(
        "--root",
        type=Path,
        required=True,
        help="dataset root (used to find annotations.json per video).",
    )
    ap.add_argument("--threshold", type=float, default=0.3)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    if not args.inp.exists():
        raise SystemExit(f"input parquet not found: {args.inp}")
    if not args.root.exists():
        raise SystemExit(f"dataset root not found: {args.root}")

    print(f"loading {args.inp} …")
    table = pq.read_table(args.inp)
    n_total = table.num_rows
    print(f"  {n_total} rows · {len(table.column_names)} cols")

    print(f"indexing annotations under {args.root} …")
    index = _build_video_index(args.root)
    print(f"  {len(index)} videos with annotations")

    video_names = table.column("video_name").to_pylist()
    centers = table.column("center_frame").to_pylist()
    old_labels = table.column("label").to_pylist()

    new_labels: list[str] = []
    fractions: list[float] = []
    missed_videos: set[str] = set()
    for vid, center in zip(video_names, centers, strict=True):
        intervals = index.get(vid)
        if intervals is None:
            missed_videos.add(vid)
            new_labels.append("other")
            fractions.append(0.0)
            continue
        f = _overlap_fraction(int(center), intervals)
        fractions.append(f)
        new_labels.append("punch" if f >= args.threshold else "other")

    if missed_videos:
        print(
            f"  warning: {len(missed_videos)} videos in parquet had no annotation match: "
            f"{sorted(missed_videos)[:3]} …"
        )

    n_punch = sum(1 for label in new_labels if label == "punch")
    n_other = n_total - n_punch
    n_old_punch = sum(1 for label in old_labels if label == "punch")
    print(
        f"  old:  punch={n_old_punch} ({n_old_punch / n_total * 100:.1f}%)  "
        f"other={n_total - n_old_punch}"
    )
    print(
        f"  new:  punch={n_punch} ({n_punch / n_total * 100:.1f}%)  other={n_other}  "
        f"(threshold={args.threshold})"
    )

    # Replace the `label` column and add `overlap_fraction` for traceability.
    cols = list(table.column_names)
    new_table = table
    label_idx = cols.index("label")
    new_table = new_table.set_column(label_idx, "label", pa.array(new_labels))
    new_table = new_table.append_column("overlap_fraction", pa.array(fractions))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(new_table, args.out)
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()

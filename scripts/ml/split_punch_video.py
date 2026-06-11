"""split_punch_video.py — Split a long punch recording into individual clips.

Usage
-----
    uv run python scripts/ml/split_punch_video.py \\
        --video data/recordings/jab_left.mp4 \\
        --label jab \\
        --hand left \\
        --subject S01 \\
        --out data/clips/

How it works
------------
1. Runs MediaPipe Pose on every frame of the long video.
2. Tracks wrist velocity (lead or rear wrist depending on --hand).
3. A punch = a spike in wrist speed above a threshold.
4. Finds the valley (rest position) between spikes to determine split points.
5. Exports each punch as an individual clip + saves metadata CSV.

Protocol for recording
----------------------
- Stand in guard (rest) for ~1 second before each punch.
- Throw the punch fully and return to guard.
- Repeat 50+ times.
- The guard rest between punches is the split boundary.

Requirements
------------
    pip install mediapipe opencv-python scipy numpy pandas
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import mediapipe as mp
import numpy as np
from scipy.signal import find_peaks, savgol_filter


# ── MediaPipe landmark indices ────────────────────────────────────────────────
# BlazePose 33-keypoint model
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12


def extract_keypoints(video_path: str) -> tuple[np.ndarray, float]:
    """Run MediaPipe on all frames, return keypoints array and fps.

    Returns
    -------
    keypoints : np.ndarray, shape [T, 33, 4]  — (x, y, z, visibility)
    fps       : float
    """
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=2,
        smooth_landmarks=True,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    )

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"  Video: {total} frames @ {fps:.1f} fps")

    keypoints: list[list[tuple[float, float, float, float]]] = []
    frame_idx = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(rgb)

        if results.pose_landmarks:
            kps = [
                (lm.x, lm.y, lm.z, lm.visibility)
                for lm in results.pose_landmarks.landmark
            ]
        else:
            # Fill with zeros if pose not detected
            kps = [(0.0, 0.0, 0.0, 0.0)] * 33

        keypoints.append(kps)
        frame_idx += 1

        if frame_idx % 100 == 0:
            print(f"  Processed {frame_idx}/{total} frames...")

    cap.release()
    pose.close()
    return np.array(keypoints, dtype=np.float32), fps


def compute_wrist_speed(
    keypoints: np.ndarray,
    hand: str,
    fps: float,
) -> np.ndarray:
    """Compute the 2D speed of the punching wrist across frames.

    Uses x,y normalised image coordinates. Speed = pixels/frame.
    """
    idx = LEFT_WRIST if hand == "left" else RIGHT_WRIST
    wrist_xy = keypoints[:, idx, :2]  # shape [T, 2]

    # Frame-to-frame displacement
    diff = np.diff(wrist_xy, axis=0)                          # [T-1, 2]
    speed = np.linalg.norm(diff, axis=1) * fps                 # pixels/sec (normalised)

    # Pad to match original length
    speed = np.concatenate([[0.0], speed])

    # Smooth to reduce noise
    if len(speed) > 11:
        speed = savgol_filter(speed, window_length=11, polyorder=3)

    return speed.clip(min=0)


def find_punch_boundaries(
    speed: np.ndarray,
    fps: float,
    min_punch_gap_sec: float = 0.5,
    min_punch_duration_sec: float = 0.1,
    speed_threshold_percentile: float = 70,
) -> list[tuple[int, int]]:
    """Find start/end frame pairs for each punch.

    Strategy
    --------
    1. Find speed peaks (each punch has one prominent peak).
    2. For each peak, walk left/right until speed drops below threshold
       — those are the start and end frames.

    Returns
    -------
    List of (start_frame, end_frame) tuples.
    """
    threshold = np.percentile(speed[speed > 0.001], speed_threshold_percentile)
    min_gap_frames = int(min_punch_gap_sec * fps)
    min_dur_frames = int(min_punch_duration_sec * fps)

    # Find prominent peaks
    peaks, props = find_peaks(
        speed,
        height=threshold,
        distance=min_gap_frames,
        prominence=threshold * 0.3,
    )

    if len(peaks) == 0:
        print("  ⚠️  No punches detected. Try lowering --threshold-percentile.")
        return []

    print(f"  Detected {len(peaks)} punch peaks.")

    boundaries = []
    low_thresh = threshold * 0.15  # below this = at rest

    for peak in peaks:
        # Walk left to find start (where speed drops below low_thresh)
        start = peak
        while start > 0 and speed[start] > low_thresh:
            start -= 1

        # Walk right to find end
        end = peak
        while end < len(speed) - 1 and speed[end] > low_thresh:
            end += 1

        # Sanity check: must be long enough
        if end - start < min_dur_frames:
            continue

        # Add padding (0.1 sec on each side) for context
        pad = int(0.1 * fps)
        start = max(0, start - pad)
        end = min(len(speed) - 1, end + pad)

        boundaries.append((start, end))

    # Merge overlapping boundaries
    merged: list[tuple[int, int]] = []
    for s, e in sorted(boundaries):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    return merged


def export_clips(
    video_path: str,
    boundaries: list[tuple[int, int]],
    out_dir: Path,
    label: str,
    hand: str,
    subject: str,
    stance: str,
    fps: float,
) -> list[dict]:
    """Write each punch segment as an individual video file.

    Returns list of metadata dicts (one per clip).
    """
    cap = cv2.VideoCapture(video_path)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = []

    for i, (start, end) in enumerate(boundaries):
        clip_name = f"{subject}_{label}_{hand}_{i:03d}.mp4"
        clip_path = out_dir / clip_name

        # Seek to start frame
        cap.set(cv2.CAP_PROP_POS_FRAMES, start)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(clip_path), fourcc, fps, (width, height))

        for _ in range(end - start + 1):
            ret, frame = cap.read()
            if not ret:
                break
            writer.write(frame)

        writer.release()

        duration_ms = int((end - start) / fps * 1000)
        metadata.append({
            "clip_name": clip_name,
            "subject_id": subject,
            "punch_type": label,
            "hand": hand,
            "stance": stance,
            "frame_start": start,
            "frame_end": end,
            "duration_ms": duration_ms,
            "source_video": Path(video_path).name,
            "quality_flag": "ok",
            "annotator_id": "auto_mediapipe",
        })

        print(f"  ✓ Clip {i+1:03d}: frames {start}–{end} ({duration_ms} ms) → {clip_name}")

    cap.release()
    return metadata


def save_metadata(metadata: list[dict], out_dir: Path, label: str, hand: str, subject: str) -> None:
    csv_path = out_dir / f"{subject}_{label}_{hand}_metadata.csv"
    if not metadata:
        return
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(metadata[0].keys()))
        writer.writeheader()
        writer.writerows(metadata)
    print(f"  Metadata saved → {csv_path}")


def visualise_detection(
    speed: np.ndarray,
    boundaries: list[tuple[int, int]],
    fps: float,
    out_path: Path,
) -> None:
    """Save a PNG plot showing speed curve + detected punch boundaries."""
    try:
        import matplotlib.pyplot as plt

        time = np.arange(len(speed)) / fps
        fig, ax = plt.subplots(figsize=(16, 4))
        ax.plot(time, speed, linewidth=0.8, color="steelblue", label="Wrist speed")

        for s, e in boundaries:
            ax.axvspan(s / fps, e / fps, alpha=0.25, color="red", label="_nolegend_")

        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Wrist speed (normalised/s)")
        ax.set_title(f"Punch detection — {out_path.stem}")
        ax.legend()
        fig.tight_layout()
        fig.savefig(str(out_path), dpi=150)
        plt.close(fig)
        print(f"  Detection plot → {out_path}")
    except ImportError:
        print("  (matplotlib not installed — skipping visualisation)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Split long punch video into individual clips.")
    parser.add_argument("--video", required=True, help="Path to the long recording")
    parser.add_argument("--label", required=True,
                        choices=["jab", "cross", "lead_hook", "rear_hook", "lead_uppercut", "rear_uppercut"],
                        help="Punch type label")
    parser.add_argument("--hand", required=True, choices=["left", "right"],
                        help="Which hand is punching")
    parser.add_argument("--subject", required=True, help="Subject ID e.g. S01")
    parser.add_argument("--stance", default="orthodox", choices=["orthodox", "southpaw"],
                        help="Fighter stance")
    parser.add_argument("--out", default="data/clips/", help="Output directory for clips")
    parser.add_argument("--threshold-percentile", type=float, default=70,
                        help="Speed percentile used as punch detection threshold (default 70). "
                             "Lower = more sensitive, higher = stricter.")
    parser.add_argument("--min-gap-sec", type=float, default=0.5,
                        help="Minimum seconds between two punches (default 0.5)")
    parser.add_argument("--plot", action="store_true",
                        help="Save a speed-curve plot showing detected boundaries")
    args = parser.parse_args()

    video_path = args.video
    out_dir = Path(args.out)

    print(f"\n🥊 Processing: {video_path}")
    print(f"   Label: {args.label}  |  Hand: {args.hand}  |  Subject: {args.subject}")

    # 1. Extract keypoints
    print("\n[1/4] Extracting pose keypoints with MediaPipe...")
    keypoints, fps = extract_keypoints(video_path)

    # 2. Compute wrist speed
    print("\n[2/4] Computing wrist speed...")
    speed = compute_wrist_speed(keypoints, args.hand, fps)
    print(f"  Max wrist speed: {speed.max():.4f}  |  Mean: {speed.mean():.4f}")

    # 3. Detect punch boundaries
    print("\n[3/4] Detecting punch boundaries...")
    boundaries = find_punch_boundaries(
        speed,
        fps,
        min_punch_gap_sec=args.min_gap_sec,
        speed_threshold_percentile=args.threshold_percentile,
    )
    print(f"  → {len(boundaries)} punches found.")

    if args.plot:
        plot_path = out_dir / f"{args.subject}_{args.label}_{args.hand}_detection.png"
        out_dir.mkdir(parents=True, exist_ok=True)
        visualise_detection(speed, boundaries, fps, plot_path)

    if not boundaries:
        print("\n❌ No punches detected. Check --threshold-percentile and recording quality.")
        return

    # 4. Export clips
    print(f"\n[4/4] Exporting {len(boundaries)} clips...")
    metadata = export_clips(
        video_path, boundaries, out_dir,
        label=args.label,
        hand=args.hand,
        subject=args.subject,
        stance=args.stance,
        fps=fps,
    )

    save_metadata(metadata, out_dir, args.label, args.hand, args.subject)

    print(f"\n✅ Done — {len(metadata)} clips saved to {out_dir}/")
    print(f"   Total duration captured: {sum(m['duration_ms'] for m in metadata) / 1000:.1f} s")


if __name__ == "__main__":
    main()

"""Side-by-side qualitative check: heuristic vs LSTM on unlabelled video.

Process the first `--max-seconds` of one or more videos with MediaPipe
Pose, then run both `HeuristicPunchDetector` (live) and `LSTMSecondPass`
(offline). Print per-clip counts, rates per minute, and the time-window
overlap between the two streams.

This is *qualitative*: there are no labels, so we can't compute
precision/recall. What we can say:
  - Did the LSTM fire at a sensible rate (boxing ≈ 0.5–2 punches/s)?
  - Does it agree with the heuristic on most events, or disagree wildly?
  - Are LSTM confidences clustered or spread out?

Run:
    uv run python -m scripts.ml.quality_check \
        --root Datasets/Dataset1 \
        --max-seconds 60
"""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import uuid4

from analyze import HeuristicPunchDetector, default_second_pass, reconcile_events
from contracts import PoseFrame


def _stream_pose_frames(
    video_path: Path, max_seconds: float, frame_stride: int = 2
) -> tuple[list[PoseFrame], float]:
    """Decode → MediaPipe Tasks PoseLandmarker → PoseFrame list.

    Returns (frames, fps).
    """
    import cv2
    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision as mp_vision

    from capture.cv.pose import ensure_pose_model
    from contracts import Landmark, WorldLandmark

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return [], 0.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    max_frames = int(max_seconds * fps)
    sid = uuid4()

    options = mp_vision.PoseLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(ensure_pose_model())),
        running_mode=mp_vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    landmarker = mp_vision.PoseLandmarker.create_from_options(options)
    frames: list[PoseFrame] = []
    try:
        i = 0
        while i < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if i % frame_stride != 0:
                i += 1
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
            t_ms = (i / fps) * 1000.0
            res = landmarker.detect_for_video(mp_image, int(t_ms))
            if not res.pose_landmarks or len(res.pose_landmarks[0]) != 33:
                i += 1
                continue
            lm = tuple(
                Landmark(
                    x=p.x,
                    y=p.y,
                    z=p.z,
                    visibility=max(0.0, min(1.0, getattr(p, "visibility", 1.0) or 0.0)),
                )
                for p in res.pose_landmarks[0]
            )
            wl = None
            wls = getattr(res, "pose_world_landmarks", None)
            if wls and len(wls) > 0 and len(wls[0]) == 33:
                wl = tuple(
                    WorldLandmark(
                        x=p.x,
                        y=p.y,
                        z=p.z,
                        visibility=max(0.0, min(1.0, getattr(p, "visibility", 1.0) or 0.0)),
                    )
                    for p in wls[0]
                )
            frames.append(
                PoseFrame(
                    session_id=sid,
                    frame_index=i,
                    t_ms=t_ms,
                    landmarks=lm,
                    world_landmarks=wl,
                )
            )
            i += 1
    finally:
        landmarker.close()
        cap.release()
    return frames, fps


def _eval_clip(video_path: Path, max_seconds: float) -> dict:
    frames, fps = _stream_pose_frames(video_path, max_seconds)
    if not frames:
        return {"video": str(video_path), "ok": False, "reason": "decode failed"}

    duration_s = (frames[-1].t_ms - frames[0].t_ms) / 1000.0
    # Live heuristic.
    det = HeuristicPunchDetector()
    live_events = []
    for f in frames:
        live_events.extend(det.feed(f))

    # Offline second-pass (LSTM if available, else stricter heuristic).
    second = default_second_pass()
    offline_events = second.detect(frames)

    consensus = reconcile_events(
        live=live_events, offline=offline_events, live_label="live", offline_label=second.name
    )
    consensus_n = sum(1 for c in consensus if c.kind == "consensus")
    live_only = sum(1 for c in consensus if c.kind == "live_only")
    offline_only = sum(1 for c in consensus if c.kind == "offline_only")

    # Confidence summary on the offline stream.
    offline_confs = sorted(e.confidence for e in offline_events)
    if offline_confs:
        med = offline_confs[len(offline_confs) // 2]
        lo = offline_confs[len(offline_confs) // 10]
        hi = offline_confs[len(offline_confs) - 1 - len(offline_confs) // 10]
    else:
        med = lo = hi = 0.0

    return {
        "video": str(video_path),
        "ok": True,
        "fps": fps,
        "duration_s": duration_s,
        "live_count": len(live_events),
        "offline_count": len(offline_events),
        "second_pass_name": second.name,
        "consensus": consensus_n,
        "live_only": live_only,
        "offline_only": offline_only,
        "live_per_min": len(live_events) / max(duration_s / 60, 1e-3),
        "offline_per_min": len(offline_events) / max(duration_s / 60, 1e-3),
        "agreement_pct": (consensus_n / max(consensus_n + live_only + offline_only, 1)) * 100,
        "offline_conf_p10_med_p90": (lo, med, hi),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="Dataset1 root")
    ap.add_argument("--max-seconds", type=float, default=60.0)
    ap.add_argument(
        "--per-cam",
        type=int,
        default=1,
        help="How many clips to sample per camera (default 1).",
    )
    args = ap.parse_args()

    if not args.root.exists():
        raise SystemExit(f"root not found: {args.root}")

    targets: list[Path] = []
    for cam_dir in sorted(d for d in args.root.iterdir() if d.is_dir()):
        clips = sorted(cam_dir.glob("*.MP4")) + sorted(cam_dir.glob("*.mp4"))
        targets.extend(clips[: args.per_cam])

    if not targets:
        raise SystemExit("no MP4 clips found under the root")

    print(f"\nrunning {len(targets)} clips × {args.max_seconds:.0f}s each\n")
    results = []
    for path in targets:
        print(f"  {path.relative_to(args.root.parent)}")
        r = _eval_clip(path, args.max_seconds)
        results.append(r)
        if not r.get("ok"):
            print(f"    skipped — {r.get('reason')}")
            continue
        print(
            f"    fps={r['fps']:.0f}  duration={r['duration_s']:.1f}s  "
            f"live={r['live_count']} ({r['live_per_min']:.1f}/min)  "
            f"offline[{r['second_pass_name']}]={r['offline_count']} "
            f"({r['offline_per_min']:.1f}/min)  "
            f"consensus={r['consensus']}  "
            f"agreement={r['agreement_pct']:.0f}%  "
            f"offline_conf p10/med/p90={r['offline_conf_p10_med_p90'][0]:.2f}/"
            f"{r['offline_conf_p10_med_p90'][1]:.2f}/"
            f"{r['offline_conf_p10_med_p90'][2]:.2f}"
        )

    print("\nsummary")
    ok = [r for r in results if r.get("ok")]
    if ok:
        live_total = sum(r["live_count"] for r in ok)
        offline_total = sum(r["offline_count"] for r in ok)
        cons_total = sum(r["consensus"] for r in ok)
        dur_total = sum(r["duration_s"] for r in ok)
        agree_pct = (
            cons_total
            / max(
                cons_total + sum(r["live_only"] for r in ok) + sum(r["offline_only"] for r in ok),
                1,
            )
            * 100
        )
        print(
            f"  total {dur_total:.0f}s · live {live_total} ({live_total / max(dur_total / 60, 1):.1f}/min) "
            f"· offline {offline_total} ({offline_total / max(dur_total / 60, 1):.1f}/min) "
            f"· consensus {cons_total} ({agree_pct:.0f}%)"
        )
        # Heuristic on what each result means
        print("\ninterpretation:")
        for r in ok:
            verdict = []
            if r["offline_per_min"] > 600:
                verdict.append("offline over-firing badly")
            elif r["offline_per_min"] < 5:
                verdict.append("offline barely firing")
            if r["agreement_pct"] < 30:
                verdict.append("low live↔offline agreement")
            elif r["agreement_pct"] > 60:
                verdict.append("good agreement")
            print(
                f"  {Path(r['video']).name}: {' · '.join(verdict) if verdict else 'plausible-looking'}"
            )
    print()


if __name__ == "__main__":
    main()

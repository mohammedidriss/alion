"""Recover a camera's pose from its recorded clip when the browser didn't send it.

The cameras track pose live in the browser and upload it at Stop. That fails
silently when the page's pose model wasn't loaded yet at Start, or the page went
off screen (a locked phone, a hidden tab): the video keeps recording, the pose
doesn't. The clip is still on disk, so the same MediaPipe pose model ("full", as
the browsers run it) is run over it here, in a background thread, and the pose
file written as if the camera had sent it — on the capture's timeline (a frame's
time in the clip + the clip's start offset).

A camera's pose counts as missing when there's no pose file or it covers under
`MIN_COVERAGE` of its clip. Where a take's pose came from is kept in take.json
(`pose_source`: device → "browser" | "video").
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from api.services import cross_check, dataset_store
from capture.cv.writer import read_pose_parquet, write_pose_parquet
from common import get_logger

log = get_logger(__name__)

MIN_COVERAGE = 0.7  # of the clip's length
BACKGROUND = True  # tests switch the thread off and call recover_take

_lock = threading.Lock()
_running: set[str] = set()


@dataclass(frozen=True)
class PoseGap:
    device_id: str
    clip: Path
    pose: Path
    start_offset_ms: float | None
    coverage: float  # 0 when there's no pose at all


def clip_length_ms(clip: Path) -> float | None:
    """A recorded clip's length (ms), from its last frame's timestamp."""
    import cv2

    cap = cv2.VideoCapture(str(clip))
    try:
        if not cap.isOpened():
            return None
        last = 0.0
        while cap.grab():
            last = cap.get(cv2.CAP_PROP_POS_MSEC)
        return last or None
    finally:
        cap.release()


def pose_span_ms(pose: Path) -> float:
    try:
        frames = read_pose_parquet(pose)
    except (OSError, ValueError):
        return 0.0
    return frames[-1].t_ms - frames[0].t_ms if len(frames) > 1 else 0.0


def take_gaps(folder: Path) -> list[PoseGap]:
    """The take's cameras whose pose is missing or covers too little of the clip."""
    gaps: list[PoseGap] = []
    take_ms = dataset_store.read_take_json(folder).get("duration_ms")
    for c in dataset_store.clips(folder):
        dev = str(c["device_id"])
        clip = dataset_store.clip_path(folder, dev, f".{c['ext']}")
        pose = dataset_store.pose_path(folder, dev)
        # The clip runs from its start offset to Stop; measure it only if unknown.
        offset = c.get("start_offset_ms") or 0.0
        length = (float(take_ms) - offset) if take_ms else clip_length_ms(clip)
        if not length or length <= 0:
            continue
        coverage = min(1.0, pose_span_ms(pose) / length) if pose.exists() else 0.0
        if coverage < MIN_COVERAGE:
            gaps.append(PoseGap(dev, clip, pose, c.get("start_offset_ms"), round(coverage, 2)))
    return gaps


def recover_clip(capture_id: UUID, gap: PoseGap) -> int:
    """Run pose over the clip and write the pose file. Returns the frames found."""
    import cv2

    from capture.cv.pose import PoseEstimator

    offset = gap.start_offset_ms or 0.0
    cap = cv2.VideoCapture(str(gap.clip))
    frames = []
    est = PoseEstimator(capture_id, fps=30.0, model="full")
    try:
        with est.open():
            while True:
                ok, bgr = cap.read()
                if not ok:
                    break
                t_clip = cap.get(cv2.CAP_PROP_POS_MSEC)
                frame = est.process(cast(Any, bgr), t_ms=t_clip + offset)
                if frame is not None:
                    frames.append(frame)
    finally:
        cap.release()
    if frames:
        frames = [f.model_copy(update={"frame_index": i}) for i, f in enumerate(frames)]
        gap.pose.parent.mkdir(parents=True, exist_ok=True)
        write_pose_parquet(gap.pose, frames)
    return len(frames)


def recover_take(take_id: UUID) -> dict[str, Any]:
    """Recover every camera of a take whose pose is missing; returns what was done."""
    folder = dataset_store.take_dir(take_id)
    if folder is None:
        return {}
    done: dict[str, Any] = {}
    sources = dict(dataset_store.read_take_json(folder).get("pose_source") or {})
    for gap in take_gaps(folder):
        n = recover_clip(take_id, gap)
        done[gap.device_id] = {"frames": n, "coverage_before": gap.coverage}
        if n:
            sources[gap.device_id] = "video"
        log.info(
            "pose.recovered",
            extra={"_ctx_capture_id": str(take_id), "_ctx_device": gap.device_id, "_ctx_frames": n},
        )
    for c in dataset_store.clips(folder):
        dev = str(c["device_id"])
        if dev not in sources and dataset_store.pose_path(folder, dev).exists():
            sources[dev] = "browser"
    dataset_store.update_take_json(folder, pose_source=sources)
    if any(v["frames"] for v in done.values()):
        cross_check.schedule("take", take_id, delay_s=0.0)  # with the recovered pose
    return done


def is_running(take_id: UUID) -> bool:
    with _lock:
        return str(take_id) in _running


# The browsers' own pose uploads land a few seconds after Stop & save completes
# the take — wait for them, so only pose that really is missing gets recovered.
AFTER_SAVE_S = 20.0


def schedule_take(take_id: UUID, *, delay_s: float = AFTER_SAVE_S) -> None:
    """Recover the take's missing pose in the background (one run at a time per take)."""
    if not BACKGROUND:
        return
    key = str(take_id)
    with _lock:
        if key in _running:
            return
        _running.add(key)

    def run() -> None:
        try:
            recover_take(take_id)
        except Exception:
            log.exception("pose.recover_failed", extra={"_ctx_capture_id": key})
        finally:
            with _lock:
                _running.discard(key)

    t = threading.Timer(delay_s, run)
    t.daemon = True
    t.name = f"pose-recover-{key[:8]}"
    t.start()

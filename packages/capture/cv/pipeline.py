"""End-to-end capture pipeline: frame source → pose → parquet (+ optional preview window).

Supports two pose backends:
- mediapipe (default): MediaPipe Pose Landmarker (33 landmarks, single person)
- yolov8: YOLOv8-Pose (17 COCO keypoints mapped to 33 MediaPipe slots)

Both produce the same PoseFrame contract so all downstream code works unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from capture.cv.pose import PoseEstimator
from capture.cv.sources import FrameSource
from capture.cv.writer import PoseParquetWriter
from contracts import PoseFrame

PoseBackend = Literal["mediapipe", "yolov8"]


@dataclass(frozen=True)
class CapturePipelineResult:
    parquet_path: Path
    frame_count: int
    duration_ms: float


def _make_estimator(
    session_id: UUID,
    fps: float,
    backend: PoseBackend,
) -> Any:
    """Create the appropriate pose estimator based on backend choice."""
    if backend == "yolov8":
        from capture.cv.pose_yolo import YOLOPoseEstimator

        return YOLOPoseEstimator(session_id, fps)
    return PoseEstimator(session_id, fps)


class CapturePipeline:
    """Pulls frames from a source, runs pose, writes parquet.

    Frames with no detected person are dropped from the parquet but still count
    toward elapsed time (frame_index keeps incrementing inside PoseEstimator).
    """

    def __init__(
        self,
        session_id: UUID,
        source: FrameSource,
        parquet_path: str | Path,
        *,
        on_frame: Callable[[PoseFrame], None] | None = None,
        on_raw_frame: Callable[[Any, PoseFrame | None], None] | None = None,
        max_frames: int | None = None,
        should_stop: Callable[[], bool] | None = None,
        pose_backend: PoseBackend = "mediapipe",
    ) -> None:
        self.session_id = session_id
        self.source = source
        self.parquet_path = Path(parquet_path)
        self._on_frame = on_frame
        self._on_raw_frame = on_raw_frame
        self._max_frames = max_frames
        self._should_stop = should_stop
        self._pose_backend = pose_backend

    def run(self) -> CapturePipelineResult:
        import logging
        import time

        log = logging.getLogger(__name__)

        writer = PoseParquetWriter(self.parquet_path)
        frame_count = 0
        last_t_ms = 0.0
        exit_reason = "source_exhausted"
        wall_t0 = time.monotonic()
        # Sources expose `open()` as a context manager but the protocol can't
        # express it; we duck-type here.
        src_ctx = self.source.open()  # type: ignore[attr-defined]
        with src_ctx as opened_source:
            estimator = _make_estimator(self.session_id, opened_source.fps, self._pose_backend)
            with estimator.open() as est:
                for raw in opened_source:
                    if self._should_stop is not None and self._should_stop():
                        exit_reason = "stop_requested"
                        break
                    pose = est.process(raw)
                    if pose is not None:
                        writer.append(pose)
                        last_t_ms = pose.t_ms
                        if self._on_frame is not None:
                            self._on_frame(pose)
                    if self._on_raw_frame is not None:
                        self._on_raw_frame(raw, pose)
                    frame_count += 1
                    if self._max_frames is not None and frame_count >= self._max_frames:
                        exit_reason = "max_frames"
                        break
        path = writer.close()
        wall_ms = (time.monotonic() - wall_t0) * 1000.0
        # Use pose-derived duration when available; fall back to wall-clock
        # so the session always records a meaningful duration even when no
        # person was detected in the frame.
        effective_duration = last_t_ms if last_t_ms > 0 else wall_ms
        log.info(
            "pipeline.exit: reason=%s frames=%d pose_duration_ms=%.1f wall_ms=%.1f",
            exit_reason,
            frame_count,
            last_t_ms,
            wall_ms,
        )
        return CapturePipelineResult(
            parquet_path=path, frame_count=frame_count, duration_ms=effective_duration
        )


def stream_pose(
    session_id: UUID,
    source: FrameSource,
    *,
    max_frames: int | None = None,
    pose_backend: PoseBackend = "mediapipe",
) -> Iterator[PoseFrame]:
    """In-memory pose stream — used for testing and the heuristic detector."""
    src_ctx = source.open()  # type: ignore[attr-defined]
    with src_ctx as opened_source:
        estimator = _make_estimator(session_id, opened_source.fps, pose_backend)
        with estimator.open() as est:
            i = 0
            for raw in opened_source:
                pose = est.process(raw)
                if pose is not None:
                    yield pose
                i += 1
                if max_frames is not None and i >= max_frames:
                    break

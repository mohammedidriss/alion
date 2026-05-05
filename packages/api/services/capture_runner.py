"""Capture runner — orchestrates a CV capture job in a background thread.

Lives in `api/` (the composition root) because it pulls together `capture`,
`analyze`, and `store`. Feature modules themselves never cross-import.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlmodel import Session as DBSession

from analyze import HeuristicPunchDetector
from capture.cv import CapturePipeline, FileSource, WebcamSource
from capture.cv.overlay import draw_pose
from capture.cv.sources import FrameSource
from common import get_logger
from contracts import PoseFrame
from store import (
    DetectionSourceEnum,
    HandEnum,
    PunchEventRepo,
    PunchEventRow,
    SessionRepo,
    SessionStatus,
)

DBFactory = Callable[[], AbstractContextManager[DBSession]]

log = get_logger(__name__)

_active_jobs: dict[UUID, threading.Thread] = {}
_stop_events: dict[UUID, threading.Event] = {}
_preview_frames: dict[UUID, bytes] = {}  # latest JPEG, written by capture thread
_active_lock = threading.Lock()

_PREVIEW_MAX_WIDTH = 480
_PREVIEW_JPEG_QUALITY = 70


def latest_preview(session_id: UUID) -> bytes | None:
    with _active_lock:
        return _preview_frames.get(session_id)


def _data_dir() -> Path:
    p = Path("data/processed")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hand_to_enum(h: str) -> HandEnum:
    return HandEnum.LEFT if h == "left" else HandEnum.RIGHT


def is_running(session_id: UUID) -> bool:
    with _active_lock:
        t = _active_jobs.get(session_id)
        return t is not None and t.is_alive()


def request_stop(session_id: UUID) -> bool:
    """Signal a running capture to stop at the next frame boundary."""
    with _active_lock:
        ev = _stop_events.get(session_id)
        if ev is None:
            return False
        ev.set()
        return True


def _run_capture(
    session_id: UUID,
    source_kind: str,
    *,
    video_path: str | None,
    db_factory: DBFactory,
    max_frames: int | None,
    stop_event: threading.Event,
) -> None:
    log.info(
        "capture.start",
        extra={"_ctx_session_id": str(session_id), "_ctx_source": source_kind},
    )
    detector = HeuristicPunchDetector()
    buffered_events: list[PunchEventRow] = []

    def on_frame(pose: PoseFrame) -> None:
        for ev in detector.feed(pose):
            buffered_events.append(
                PunchEventRow(
                    session_id=ev.session_id,
                    t_ms=ev.t_ms,
                    hand=_hand_to_enum(ev.hand),
                    velocity_ms=ev.velocity_ms,
                    detected_by=DetectionSourceEnum(ev.detected_by),
                    confidence=ev.confidence,
                )
            )

    def on_raw_frame(raw: Any, pose: PoseFrame | None) -> None:
        """Encode a downscaled BGR frame with skeleton overlay for the preview MJPEG stream."""
        import cv2

        # Copy so we don't mutate the source frame the pipeline still cares about.
        frame = raw.copy()
        h, w = frame.shape[:2]
        if w > _PREVIEW_MAX_WIDTH:
            scale = _PREVIEW_MAX_WIDTH / w
            frame = cv2.resize(frame, (_PREVIEW_MAX_WIDTH, int(h * scale)))
            # Landmark coords are in normalized [0,1], so they still map
            # correctly to the resized frame — no adjustment needed in draw_pose.
        draw_pose(frame, pose)
        ok, buf = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), _PREVIEW_JPEG_QUALITY]
        )
        if not ok:
            return
        with _active_lock:
            _preview_frames[session_id] = buf.tobytes()

    parquet_path = _data_dir() / f"{session_id}.pose.parquet"
    source: FrameSource
    if source_kind == "live_webcam":
        source = WebcamSource(index=0)
    elif source_kind == "uploaded_video":
        if not video_path:
            raise ValueError("uploaded_video requires video_path")
        source = FileSource(video_path)
    else:
        raise ValueError(f"unsupported source: {source_kind}")

    try:
        with db_factory() as db:
            SessionRepo(db).update_status(session_id, SessionStatus.CAPTURING)

        pipeline = CapturePipeline(
            session_id=session_id,
            source=source,
            parquet_path=parquet_path,
            on_frame=on_frame,
            on_raw_frame=on_raw_frame,
            max_frames=max_frames,
            should_stop=stop_event.is_set,
        )
        result = pipeline.run()

        with db_factory() as db:
            PunchEventRepo(db).add_many(buffered_events)
            SessionRepo(db).attach_artifacts(
                session_id,
                pose_parquet_path=str(result.parquet_path),
                frame_count=result.frame_count,
                duration_ms=result.duration_ms,
            )
            SessionRepo(db).update_status(session_id, SessionStatus.COMPLETED, end=True)

        log.info(
            "capture.done",
            extra={
                "_ctx_session_id": str(session_id),
                "_ctx_frames": result.frame_count,
                "_ctx_punches": len(buffered_events),
            },
        )
    except ModuleNotFoundError as e:
        # CV deps not installed (typical in the default Docker image — MediaPipe
        # has no linux/aarch64 wheel). Map to a user-friendly reason.
        reason = (
            "Video capture isn't available on this server. "
            "MediaPipe and OpenCV aren't installed in this environment "
            "(likely the default Docker image). Run capture on the host with "
            "`uv run python scripts/record_live.py --fighter <id>` instead."
        )
        log.exception(
            "capture.failed (cv unavailable): %s", e, extra={"_ctx_session_id": str(session_id)}
        )
        with db_factory() as db:
            SessionRepo(db).update_status(
                session_id, SessionStatus.FAILED, end=True, failure_reason=reason
            )
    except Exception as e:
        log.exception("capture.failed: %s", e, extra={"_ctx_session_id": str(session_id)})
        with db_factory() as db:
            SessionRepo(db).update_status(
                session_id, SessionStatus.FAILED, end=True, failure_reason=str(e)
            )
    finally:
        with _active_lock:
            _active_jobs.pop(session_id, None)
            _stop_events.pop(session_id, None)
            _preview_frames.pop(session_id, None)


def start_capture(
    session_id: UUID,
    source_kind: str,
    db_factory: DBFactory,
    *,
    video_path: str | None = None,
    max_frames: int | None = None,
) -> bool:
    """Spawn the capture in a background thread. Returns False if already running."""
    with _active_lock:
        if session_id in _active_jobs and _active_jobs[session_id].is_alive():
            return False
        stop_event = threading.Event()
        _stop_events[session_id] = stop_event
        t = threading.Thread(
            target=_run_capture,
            args=(session_id, source_kind),
            kwargs={
                "video_path": video_path,
                "db_factory": db_factory,
                "max_frames": max_frames,
                "stop_event": stop_event,
            },
            daemon=True,
            name=f"capture-{session_id}",
        )
        _active_jobs[session_id] = t
        t.start()
    return True


def run_capture_sync(
    db: DBSession,
    session_id: UUID,
    source_kind: str,
    *,
    video_path: str | None = None,
    max_frames: int | None = None,
) -> None:
    """Synchronous variant — used by CLI scripts where blocking is fine."""
    from collections.abc import Iterator
    from contextlib import contextmanager

    @contextmanager
    def factory() -> Iterator[DBSession]:
        yield db

    _run_capture(
        session_id,
        source_kind,
        video_path=video_path,
        db_factory=factory,
        max_frames=max_frames,
        stop_event=threading.Event(),
    )

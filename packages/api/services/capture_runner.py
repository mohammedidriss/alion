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

from analyze import HeuristicPunchDetector, classify_punch_type, refine_peak_velocity
from capture.cv import CapturePipeline, FileSource, WebcamSource
from capture.cv.overlay import draw_pose
from capture.cv.sources import FrameSource
from common import SessionClock, get_logger
from contracts import PoseFrame
from store import (
    DetectionSourceEnum,
    HandEnum,
    LeadOrRearEnum,
    PunchEventRepo,
    PunchEventRow,
    PunchTypeEnum,
    SessionRepo,
    SessionStatus,
    VelocitySourceEnum,
)

DBFactory = Callable[[], AbstractContextManager[DBSession]]

log = get_logger(__name__)

_active_jobs: dict[UUID, threading.Thread] = {}
_stop_events: dict[UUID, threading.Event] = {}
_pause_events: dict[UUID, threading.Event] = {}
_preview_frames: dict[UUID, bytes] = {}  # latest JPEG, written by capture thread
# Per-session T_0 reference. Other modalities (HRV BLE driver, IMU when wired)
# fetch this via clock_for(session_id) so every stream tags samples with
# offsets relative to the same instant. See common/time_utils.SessionClock.
_session_clocks: dict[UUID, SessionClock] = {}
_active_lock = threading.Lock()

_PREVIEW_MAX_WIDTH = 480
_PREVIEW_JPEG_QUALITY = 70


def latest_preview(session_id: UUID) -> bytes | None:
    with _active_lock:
        return _preview_frames.get(session_id)


def clock_for(session_id: UUID) -> SessionClock | None:
    """Return the SessionClock anchored when this session started capturing.

    Returns None if capture hasn't started or has already ended. Used by the
    HRV/IMU runners to convert their externally-timestamped samples into
    offsets relative to the same T_0 the CV pipeline uses.
    """
    with _active_lock:
        return _session_clocks.get(session_id)


def _data_dir() -> Path:
    p = Path("data/processed")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _hand_to_enum(h: str) -> HandEnum:
    return HandEnum.LEFT if h == "left" else HandEnum.RIGHT


def _refined_peak_for_event(pose_history: list[PoseFrame], hand: str) -> float | None:
    """Build (t_ms, x, y, z) samples for the punching wrist and run sub-frame refinement."""
    if len(pose_history) < 4:
        return None
    wrist_idx = 15 if hand == "left" else 16
    use_world = all(f.world_landmarks is not None for f in pose_history)
    samples: list[tuple[float, float, float, float]] = []
    for f in pose_history:
        if use_world and f.world_landmarks is not None:
            wlm = f.world_landmarks[wrist_idx]
            if wlm.visibility < 0.4:
                continue
            samples.append((f.t_ms, wlm.x, wlm.y, wlm.z))
        else:
            lm = f.landmarks[wrist_idx]
            if lm.visibility < 0.4:
                continue
            # Image-plane mode: scale by an assumed body width so the result
            # is comparable to the detector's m/s number. Crude but matches
            # the legacy fallback path.
            samples.append((f.t_ms, lm.x * 0.45, lm.y * 0.45, lm.z * 0.45))
    if len(samples) < 4:
        return None
    return refine_peak_velocity(samples)


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
        # If we were paused, unpause first so the loop can see the stop flag
        # and exit cleanly instead of sleeping forever.
        pause = _pause_events.get(session_id)
        if pause is not None and not pause.is_set():
            pause.set()
        return True


def request_pause(session_id: UUID) -> bool:
    """Request the running capture to pause at the next frame boundary."""
    with _active_lock:
        ev = _pause_events.get(session_id)
        if ev is None:
            return False
        ev.clear()  # clear = paused (the run-loop blocks on .wait())
        return True


def request_resume(session_id: UUID) -> bool:
    """Resume a paused capture."""
    with _active_lock:
        ev = _pause_events.get(session_id)
        if ev is None:
            return False
        ev.set()  # set = running
        return True


def is_paused(session_id: UUID) -> bool:
    with _active_lock:
        ev = _pause_events.get(session_id)
        return ev is not None and not ev.is_set()


def _run_capture(
    session_id: UUID,
    source_kind: str,
    *,
    video_path: str | None,
    db_factory: DBFactory,
    max_frames: int | None,
    stop_event: threading.Event,
    pause_event: threading.Event,
    stance: str | None = None,
    camera_index: int = 0,
) -> None:
    log.info(
        "capture.start",
        extra={
            "_ctx_session_id": str(session_id),
            "_ctx_source": source_kind,
            "_ctx_camera_index": camera_index,
        },
    )
    detector = HeuristicPunchDetector(stance=stance)
    buffered_events: list[PunchEventRow] = []
    # Rolling pose history feeds the punch-type classifier (~last 8 frames).
    pose_history: list[PoseFrame] = []
    history_len = 8

    def on_frame(pose: PoseFrame) -> None:
        pose_history.append(pose)
        if len(pose_history) > history_len:
            pose_history.pop(0)
        for ev in detector.feed(pose):
            ptype = classify_punch_type(pose_history, ev.hand, stance)
            # Refine the velocity using sub-frame interpolation across the
            # recent pose history. We pull the wrist's world-coord trajectory
            # (or image-plane fallback) and feed it to the refiner. If we get
            # a higher peak than the detector reported, we use the refined
            # value; otherwise stick with the detector's value.
            refined_v = _refined_peak_for_event(pose_history, ev.hand)
            final_v = max(ev.velocity_ms, refined_v) if refined_v is not None else ev.velocity_ms
            buffered_events.append(
                PunchEventRow(
                    session_id=ev.session_id,
                    t_ms=ev.t_ms,
                    hand=_hand_to_enum(ev.hand),
                    lead_or_rear=LeadOrRearEnum(ev.lead_or_rear) if ev.lead_or_rear else None,
                    velocity_ms=round(final_v, 2),
                    velocity_source=VelocitySourceEnum(ev.velocity_source),
                    punch_type=PunchTypeEnum(ptype) if ptype else None,
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
        source = WebcamSource(index=camera_index)
    elif source_kind == "uploaded_video":
        if not video_path:
            raise ValueError("uploaded_video requires video_path")
        source = FileSource(video_path)
    else:
        raise ValueError(f"unsupported source: {source_kind}")

    try:
        with db_factory() as db:
            SessionRepo(db).update_status(session_id, SessionStatus.CAPTURING)

        # Anchor T_0 the moment we transition to CAPTURING. From here on,
        # any other modality (HRV BLE, IMU) can fetch this clock via
        # clock_for(session_id) and tag its samples with offsets relative
        # to the same instant. Pre-condition for cross-stream alignment.
        with _active_lock:
            _session_clocks[session_id] = SessionClock.start()

        # The pipeline checks `should_stop` each frame; we use it as a
        # combined "block-while-paused, return-true-to-quit" signal so the
        # capture thread can pause without spinning.
        def should_stop_or_pause() -> bool:
            # Block here while paused. Returns immediately if the pause
            # event is set (running) or wakes up when set/closed.
            pause_event.wait()
            return stop_event.is_set()

        pipeline = CapturePipeline(
            session_id=session_id,
            source=source,
            parquet_path=parquet_path,
            on_frame=on_frame,
            on_raw_frame=on_raw_frame,
            max_frames=max_frames,
            should_stop=should_stop_or_pause,
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

        # Summarise near-misses so we can see WHY rejected peaks didn't fire.
        # Tuning the heuristic without this is guesswork.
        nm_counts: dict[str, int] = {}
        for nm in detector.near_misses:
            r = str(nm["reason"])
            nm_counts[r] = nm_counts.get(r, 0) + 1
        log.info(
            "capture.done",
            extra={
                "_ctx_session_id": str(session_id),
                "_ctx_frames": result.frame_count,
                "_ctx_punches": len(buffered_events),
                "_ctx_near_misses": len(detector.near_misses),
                "_ctx_near_miss_breakdown": nm_counts,
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
            _pause_events.pop(session_id, None)
            _preview_frames.pop(session_id, None)
            _session_clocks.pop(session_id, None)


def start_capture(
    session_id: UUID,
    source_kind: str,
    db_factory: DBFactory,
    *,
    video_path: str | None = None,
    max_frames: int | None = None,
    stance: str | None = None,
    camera_index: int = 0,
) -> bool:
    """Spawn the capture in a background thread. Returns False if already running."""
    with _active_lock:
        if session_id in _active_jobs and _active_jobs[session_id].is_alive():
            return False
        stop_event = threading.Event()
        pause_event = threading.Event()
        pause_event.set()  # set = running; clear = paused (the loop blocks on .wait())
        _stop_events[session_id] = stop_event
        _pause_events[session_id] = pause_event
        t = threading.Thread(
            target=_run_capture,
            args=(session_id, source_kind),
            kwargs={
                "video_path": video_path,
                "db_factory": db_factory,
                "max_frames": max_frames,
                "stop_event": stop_event,
                "pause_event": pause_event,
                "stance": stance,
                "camera_index": camera_index,
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

    pause = threading.Event()
    pause.set()  # never paused in sync mode
    _run_capture(
        session_id,
        source_kind,
        video_path=video_path,
        db_factory=factory,
        max_frames=max_frames,
        stop_event=threading.Event(),
        pause_event=pause,
    )

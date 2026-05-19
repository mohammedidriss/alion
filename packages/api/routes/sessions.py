"""Session CRUD + capture orchestration."""

from __future__ import annotations

import asyncio
import csv
import datetime
import io
import math
import tempfile
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from analyze import compute_score, mean_hr_bpm, rmssd_ms, sdnn_ms
from api.deps import db_session, fighter_repo, punch_event_repo, resolve_gym_id, session_repo
from api.routes.auth import get_current_user, require_current_user
from api.services import capture_runner
from capture.hrv import parse_rr_csv
from contracts import HRSample
from store import (
    AttachmentKind,
    FighterRepo,
    PunchEventRepo,
    SessionAttachment,
    SessionAttachmentRead,
    SessionRepo,
    SessionSourceEnum,
    SessionStatus,
    User,
)
from store.models import (
    PunchEventRead,
    SessionCreate,
    SessionRead,
)
from studies import DetectedPunch, confusion_matrix, match_events
from studies.evaluation import load_labels

router = APIRouter(
    prefix="/sessions",
    tags=["sessions"],
    dependencies=[Depends(require_current_user)],
)

# Separate router for endpoints that can't send auth headers (e.g. <img src>).
# The unguessable session UUID serves as the access control.
preview_router = APIRouter(prefix="/sessions", tags=["sessions"])

_VIDEO_DIR = Path("data/raw/uploaded")


class CaptureStartRequest(BaseModel):
    max_frames: int | None = None
    camera_index: int = 0
    pose_backend: Literal["mediapipe", "yolov8"] = "mediapipe"


class CaptureStatusResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    is_running: bool
    is_paused: bool = False
    frame_count: int
    duration_ms: float
    punch_count: int


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(data: SessionCreate, repo: SessionRepo = Depends(session_repo)) -> SessionRead:
    row = repo.create(data)
    return SessionRead.model_validate(row, from_attributes=True)


def _purge_stale_pending(repo: SessionRepo) -> int:
    """Delete pending sessions with 0 frames that are older than 10 minutes."""
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
    all_sessions = repo.list_all()
    deleted = 0
    for s in all_sessions:
        if s.status == SessionStatus.PENDING and s.frame_count == 0 and s.started_at < cutoff:
            repo.delete(s.id)
            deleted += 1
    return deleted


@router.delete("/stale-pending")
def delete_stale_pending(repo: SessionRepo = Depends(session_repo)) -> dict:
    """Explicitly purge old empty pending sessions."""
    deleted = _purge_stale_pending(repo)
    return {"deleted": deleted}


@router.get("", response_model=list[SessionRead])
def list_sessions(
    fighter_id: UUID | None = None,
    repo: SessionRepo = Depends(session_repo),
    current_user: User | None = Depends(get_current_user),
    session: DBSession = Depends(db_session),
    frepo: FighterRepo = Depends(fighter_repo),
) -> list[SessionRead]:
    # Auto-clean stale pending sessions on every list call.
    _purge_stale_pending(repo)

    # Gym managers can only see sessions for their gym's fighters
    if current_user and current_user.role == "gym_manager":
        scoped_gym = resolve_gym_id(current_user, session)
        if scoped_gym:
            gym_fighters = frepo.list_for_gym(scoped_gym)
            gym_fighter_ids = {f.id for f in gym_fighters}
            all_rows = repo.list_for_fighter(fighter_id) if fighter_id else repo.list_all()
            rows = [s for s in all_rows if s.fighter_id in gym_fighter_ids]
            return [SessionRead.model_validate(s, from_attributes=True) for s in rows]

    rows = repo.list_for_fighter(fighter_id) if fighter_id else repo.list_all()
    return [SessionRead.model_validate(s, from_attributes=True) for s in rows]


@router.get("/{session_id}", response_model=SessionRead)
def get_session_route(session_id: UUID, repo: SessionRepo = Depends(session_repo)) -> SessionRead:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionRead.model_validate(row, from_attributes=True)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session_route(session_id: UUID, repo: SessionRepo = Depends(session_repo)) -> None:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if capture_runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="capture is running — stop it first")
    # Best-effort artifact cleanup. We don't fail the delete if a file is gone.
    for path_str in (row.video_path, row.pose_parquet_path):
        if path_str:
            try:
                Path(path_str).unlink(missing_ok=True)
            except OSError:
                pass
    if not repo.delete(session_id):
        raise HTTPException(status_code=404, detail="session not found")


@router.post("/{session_id}/upload", response_model=SessionRead)
def upload_video(
    session_id: UUID,
    file: UploadFile = File(...),
    repo: SessionRepo = Depends(session_repo),
) -> SessionRead:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if row.source != SessionSourceEnum.UPLOADED_VIDEO:
        raise HTTPException(
            status_code=400, detail=f"session source is {row.source}, not uploaded_video"
        )
    _VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename or "").suffix or ".mp4"
    dest = _VIDEO_DIR / f"{session_id}{suffix}"
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            out.write(chunk)
    updated = repo.attach_artifacts(session_id, video_path=str(dest))
    assert updated is not None
    return SessionRead.model_validate(updated, from_attributes=True)


@router.post("/{session_id}/capture/reprocess", response_model=CaptureStatusResponse)
def reprocess_capture_route(
    session_id: UUID,
    body: CaptureStartRequest | None = None,
    repo: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> CaptureStatusResponse:
    """Re-run the pipeline on an already-uploaded video. Wipes prior events
    so the new run replaces them. Useful for re-tuning the detector.
    """
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if row.source != SessionSourceEnum.UPLOADED_VIDEO or not row.video_path:
        raise HTTPException(
            status_code=400, detail="reprocess only available for uploaded_video sessions"
        )
    if capture_runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="capture already running")

    # Wipe previous detections so the new run is the source of truth.
    from sqlmodel import delete as sqlmodel_delete

    from store import PunchEventRow

    db.exec(
        sqlmodel_delete(PunchEventRow).where(PunchEventRow.session_id == session_id)  # type: ignore[arg-type]
    )
    repo.update_status(session_id, SessionStatus.PENDING)
    db.commit()

    # Reuse the same flow as start_capture_route by routing through it.
    return start_capture_route(session_id=session_id, body=body, repo=repo, events=events, db=db)


@router.post("/{session_id}/capture/start", response_model=CaptureStatusResponse)
def start_capture_route(
    session_id: UUID,
    body: CaptureStartRequest | None = None,
    repo: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> CaptureStatusResponse:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    # RQ2 condition gate — block CV capture for non-CV conditions.
    if row.study_condition is not None:
        from store import StudyConditionEnum

        cond = StudyConditionEnum(row.study_condition)
        if not cond.allows_cv:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"CV capture is not allowed for study condition '{row.study_condition}'. "
                    f"Allowed modalities: {', '.join(cond.allowed_modalities) or 'none'}."
                ),
            )
    if capture_runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="capture already running")

    if row.source == SessionSourceEnum.UPLOADED_VIDEO and not row.video_path:
        raise HTTPException(status_code=400, detail="upload a video first")

    @contextmanager
    def factory() -> Iterator[DBSession]:
        from store import get_session as _gs

        gen = _gs()
        s = next(gen)
        try:
            yield s
        finally:
            try:
                next(gen)
            except StopIteration:
                pass

    # Look up fighter stance so the detector can label lead/rear hand.
    from store import FighterRepo as _FighterRepo

    fighter = _FighterRepo(db).get(row.fighter_id)
    stance_str = fighter.stance.value if fighter else None

    started = capture_runner.start_capture(
        session_id,
        row.source.value,
        factory,
        video_path=row.video_path,
        max_frames=body.max_frames if body else None,
        stance=stance_str,
        camera_index=body.camera_index if body else 0,
        pose_backend=body.pose_backend if body else "mediapipe",
    )
    if not started:
        raise HTTPException(status_code=409, detail="capture already running")

    return CaptureStatusResponse(
        session_id=session_id,
        status=SessionStatus.CAPTURING,
        is_running=True,
        frame_count=0,
        duration_ms=0.0,
        punch_count=events.count_for_session(session_id),
    )


@router.post("/{session_id}/capture/stop", response_model=CaptureStatusResponse)
def stop_capture_route(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
) -> CaptureStatusResponse:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not capture_runner.request_stop(session_id):
        raise HTTPException(status_code=409, detail="no capture running")
    return CaptureStatusResponse(
        session_id=session_id,
        status=row.status,
        is_running=True,  # actual stop happens at next frame boundary
        frame_count=row.frame_count,
        duration_ms=row.duration_ms,
        punch_count=events.count_for_session(session_id),
    )


@router.post("/{session_id}/capture/pause", response_model=CaptureStatusResponse)
def pause_capture_route(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
) -> CaptureStatusResponse:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not capture_runner.request_pause(session_id):
        raise HTTPException(status_code=409, detail="no capture running")
    return CaptureStatusResponse(
        session_id=session_id,
        status=row.status,
        is_running=True,
        frame_count=row.frame_count,
        duration_ms=row.duration_ms,
        punch_count=events.count_for_session(session_id),
    )


@router.post("/{session_id}/capture/resume", response_model=CaptureStatusResponse)
def resume_capture_route(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
) -> CaptureStatusResponse:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not capture_runner.request_resume(session_id):
        raise HTTPException(status_code=409, detail="no capture running")
    return CaptureStatusResponse(
        session_id=session_id,
        status=row.status,
        is_running=True,
        frame_count=row.frame_count,
        duration_ms=row.duration_ms,
        punch_count=events.count_for_session(session_id),
    )


@router.get("/{session_id}/capture/status", response_model=CaptureStatusResponse)
def capture_status(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
) -> CaptureStatusResponse:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return CaptureStatusResponse(
        session_id=session_id,
        status=row.status,
        is_running=capture_runner.is_running(session_id),
        is_paused=capture_runner.is_paused(session_id),
        frame_count=row.frame_count,
        duration_ms=row.duration_ms,
        punch_count=events.count_for_session(session_id),
    )


@preview_router.get("/{session_id}/preview")
async def preview_stream(session_id: UUID) -> StreamingResponse:
    """MJPEG stream of the latest captured frame with skeleton overlay.

    Consumed natively by <img src="..."> in the dashboard. Closes when capture
    finishes (the buffer disappears). Frame rate is bounded by both the capture
    pipeline (~30fps) and a small server-side throttle.
    """
    boundary = "frame"

    async def gen() -> AsyncIterator[bytes]:
        last: bytes | None = None
        empty_streak = 0
        # Send a 1x1 placeholder until real frames arrive, so the browser
        # doesn't render broken-image until capture starts producing frames.
        while True:
            frame = capture_runner.latest_preview(session_id)
            if frame is None:
                empty_streak += 1
                # Capture finished and buffer was cleaned — close the stream.
                if not capture_runner.is_running(session_id) and empty_streak > 5:
                    return
                await asyncio.sleep(0.1)
                continue
            empty_streak = 0
            if frame is not last:
                yield (
                    (
                        f"--{boundary}\r\n"
                        f"Content-Type: image/jpeg\r\n"
                        f"Content-Length: {len(frame)}\r\n\r\n"
                    ).encode("ascii")
                    + frame
                    + b"\r\n"
                )
                last = frame
            await asyncio.sleep(1 / 15)  # cap preview at ~15 fps

    return StreamingResponse(
        gen(),
        media_type=f"multipart/x-mixed-replace; boundary={boundary}",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{session_id}/events", response_model=list[PunchEventRead])
def list_events(
    session_id: UUID, events: PunchEventRepo = Depends(punch_event_repo)
) -> list[PunchEventRead]:
    rows = events.list_for_session(session_id)
    return [PunchEventRead.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{session_id}/events.csv")
def export_events_csv(
    session_id: UUID,
    events: PunchEventRepo = Depends(punch_event_repo),
    repo: SessionRepo = Depends(session_repo),
) -> Response:
    """Download punch events as a CSV — one row per event, header included.

    Columns are stable: index, t_ms, time_iso, hand, lead_or_rear,
    punch_type, velocity_ms, velocity_source, confidence, detected_by.
    """
    sess = repo.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")
    rows = events.list_for_session(session_id)

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "index",
            "t_ms",
            "time_iso",
            "hand",
            "lead_or_rear",
            "punch_type",
            "velocity_ms",
            "velocity_source",
            "confidence",
            "detected_by",
        ]
    )
    from datetime import UTC, datetime

    started_ms = sess.started_at.timestamp() * 1000.0
    for i, r in enumerate(rows):
        iso = datetime.fromtimestamp((started_ms + r.t_ms) / 1000.0, tz=UTC).isoformat()
        writer.writerow(
            [
                i + 1,
                f"{r.t_ms:.2f}",
                iso,
                r.hand.value,
                r.lead_or_rear.value if r.lead_or_rear else "",
                r.punch_type.value if r.punch_type else "",
                f"{r.velocity_ms:.2f}",
                r.velocity_source.value,
                f"{r.confidence:.2f}",
                r.detected_by.value,
            ]
        )

    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="alion-{session_id}-events.csv"'},
    )


class SessionAnnotation(BaseModel):
    """Patch payload — every field optional. Send only the keys you want
    to change. Used for notes, round-structure, and RQ2 study condition."""

    notes: str | None = None
    round_count: int | None = None
    round_duration_s: int | None = None
    rest_duration_s: int | None = None
    study_condition: str | None = None  # one of StudyConditionEnum values


@router.patch("/{session_id}", response_model=SessionRead)
def annotate_session(
    session_id: UUID,
    data: SessionAnnotation,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> SessionRead:
    """Update notes and/or round configuration. Only fields the client
    explicitly sends are applied (None means "don't change")."""
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    patch = data.model_dump(exclude_unset=True)
    for k, v in patch.items():
        setattr(row, k, v)
    db.add(row)
    db.commit()
    db.refresh(row)
    return SessionRead.model_validate(row, from_attributes=True)


class PerformanceResponse(BaseModel):
    session_id: UUID
    peak_velocity_p90: float
    ppm: float
    duration_min: float
    score: float
    punch_count: int
    baseline_rmssd_ms: float | None = None
    baseline_sdnn_ms: float | None = None
    baseline_mean_hr_bpm: float | None = None
    trimp_score: float | None = None
    trimp_duration_min: float | None = None


class CoachAdviceResponse(BaseModel):
    summary: str
    action_items: list[str]


@router.post("/{session_id}/baseline/upload", response_model=SessionRead)
async def upload_baseline(
    session_id: UUID,
    file: UploadFile = File(...),
    repo: SessionRepo = Depends(session_repo),
) -> SessionRead:
    """Upload a 5-min resting RR-interval CSV; computes RMSSD/SDNN/mean HR
    over the whole file and persists them on the session."""
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="empty upload")
    # parse_rr_csv reads from a Path — write to a temp file.
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
        tmp.write(body)
        tmp_path = Path(tmp.name)
    try:
        samples = parse_rr_csv(tmp_path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"invalid RR CSV: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)
    if len(samples) < 4:
        raise HTTPException(status_code=400, detail="need at least 4 RR intervals")
    hr_samples = [
        HRSample(session_id=session_id, t_ms=t, rr_ms=rr, hr_bpm=60_000.0 / rr) for t, rr in samples
    ]
    row = repo.attach_baseline(
        session_id,
        rmssd_ms=round(rmssd_ms(hr_samples), 2),
        sdnn_ms=round(sdnn_ms(hr_samples), 2),
        mean_hr_bpm=round(mean_hr_bpm(hr_samples), 2),
    )
    assert row is not None
    return SessionRead.model_validate(row, from_attributes=True)


@router.get("/{session_id}/performance", response_model=PerformanceResponse)
def session_performance(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> PerformanceResponse:
    row = sessions.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    rows = events.list_for_session(session_id)
    velocities = [e.velocity_ms for e in rows]
    score = compute_score(velocities, row.duration_ms)

    import datetime

    from sqlmodel import select

    from analyze.load import compute_trimp, estimate_hr_max
    from store.models import Fighter, HRSampleRow

    fighter = db.get(Fighter, row.fighter_id)
    hr_samples = list(
        db.exec(select(HRSampleRow.hr_bpm).where(HRSampleRow.session_id == session_id)).all()
    )

    trimp_score = None
    trimp_duration_min = None
    if row.baseline_mean_hr_bpm and hr_samples and row.duration_ms > 0:
        age_years = 25.0
        if fighter and fighter.dob:
            age_years = (datetime.datetime.now(datetime.UTC).date() - fighter.dob).days / 365.25
        hr_max = estimate_hr_max(age_years)
        sex: Literal["male", "female"] = "female" if fighter and fighter.sex == "female" else "male"
        res = compute_trimp(
            hr_samples,
            duration_min=row.duration_ms / 60000.0,
            hr_rest_bpm=row.baseline_mean_hr_bpm,
            hr_max_bpm=hr_max,
            sex=sex,
        )
        if res:
            trimp_score = res.trimp
            trimp_duration_min = res.duration_min

    return PerformanceResponse(
        session_id=session_id,
        peak_velocity_p90=score.peak_velocity_p90,
        ppm=score.ppm,
        duration_min=score.duration_min,
        score=score.score,
        punch_count=len(rows),
        baseline_rmssd_ms=row.baseline_rmssd_ms,
        baseline_sdnn_ms=row.baseline_sdnn_ms,
        baseline_mean_hr_bpm=row.baseline_mean_hr_bpm,
        trimp_score=trimp_score,
        trimp_duration_min=trimp_duration_min,
    )


@router.post("/{session_id}/advice", response_model=CoachAdviceResponse)
async def get_session_advice(
    session_id: UUID,
    payload_mode: Literal["cv", "hrv", "imu", "fused"] = "fused",
    force_regenerate: bool = False,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> CoachAdviceResponse:
    """Generate corner advice from a chosen payload subset.

    `payload_mode` is the RQ1 study lever — same LLM, same prompt, but a
    sliced view of the per-round fused export. Lets us measure marginal
    advice quality contributed by each modality.

    When a session has a `study_condition` set (RQ2), the condition gates
    which modalities the LLM may see.  ``coach_only`` sessions get no AI
    advice at all — that's the control.

    Cached per `(session_id, payload_mode, prompt_version)` so every
    rater scores the same generation. Pass `force_regenerate=true` to
    bypass and overwrite the cache.
    """
    import json as _json

    from sqlmodel import select as _select

    from coach import CORNER_ADVICE_SYSTEM_PROMPT, PROMPT_VERSION, generate_corner_advice
    from store import CoachAdviceCacheRow, PayloadModeEnum

    row = sessions.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")

    # RQ2 condition gate — coach_only sessions get no AI advice (control).
    if row.study_condition is not None:
        from store import StudyConditionEnum

        cond = StudyConditionEnum(row.study_condition)
        if not cond.allows_ai_advice:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"AI advice is disabled for study condition '{row.study_condition}'. "
                    "This session is in the coach-only control group."
                ),
            )

    mode_enum = PayloadModeEnum(payload_mode)
    cache_stmt = _select(CoachAdviceCacheRow).where(
        CoachAdviceCacheRow.session_id == session_id,
        CoachAdviceCacheRow.payload_mode == mode_enum,
        CoachAdviceCacheRow.prompt_version == PROMPT_VERSION,
    )
    cached = db.exec(cache_stmt).first()
    # Treat cached LLM-failure rows as cache misses so a transient
    # outage doesn't get stuck in the cache forever. The caller still
    # gets a fresh attempt on the next click.
    cached_is_failure = cached is not None and cached.summary.lower().startswith(
        "failed to connect to llm"
    )
    if cached is not None and not force_regenerate and not cached_is_failure:
        return CoachAdviceResponse(
            summary=cached.summary,
            action_items=_json.loads(cached.action_items_json),
        )

    fused = rounds_export(session_id, sessions, events, db)
    rounds_payload: list[dict[str, object]] = []
    for r in fused.rounds:
        block: dict[str, object] = {
            "round": r.round_number,
            "duration_s": r.duration_ms / 1000.0,
        }
        if payload_mode in ("cv", "fused"):
            block["cv"] = r.cv.model_dump(exclude={"events"})
        if payload_mode in ("hrv", "fused"):
            block["hrv"] = r.hrv.model_dump()
        if payload_mode in ("imu", "fused"):
            block["imu"] = r.imu.model_dump()
        rounds_payload.append(block)

    payload = {
        "session_id": str(session_id),
        "payload_mode": payload_mode,
        "rounds": rounds_payload,
    }
    session_data = _json.dumps(payload)

    advice = await generate_corner_advice(CORNER_ADVICE_SYSTEM_PROMPT, session_data)

    # Upsert cache, but ONLY for successful generations. LLM-connection
    # errors return a `summary` like "Failed to connect to LLM (...)";
    # caching those would persist a transient outage indefinitely.
    is_failure = advice.summary.lower().startswith("failed to connect to llm")
    if cached is not None:
        db.delete(cached)
        db.commit()
    if not is_failure:
        db.add(
            CoachAdviceCacheRow(
                session_id=session_id,
                payload_mode=mode_enum,
                prompt_version=PROMPT_VERSION,
                summary=advice.summary,
                action_items_json=_json.dumps(advice.action_items),
            )
        )
        db.commit()

    return CoachAdviceResponse(
        summary=advice.summary,
        action_items=advice.action_items,
    )


# ---------------------------------------------------------------------------
# Per-round structured export — for downstream LLM/AI analysis
# ---------------------------------------------------------------------------


class RoundEventOut(BaseModel):
    t_ms: float
    hand: str
    velocity_ms: float
    confidence: float | None = None


class RoundCvBlock(BaseModel):
    punch_count: int
    peak_velocity_ms: float | None
    ppm: float | None
    events: list[RoundEventOut]


class RoundHrvBlock(BaseModel):
    sample_count: int
    mean_hr_bpm: float | None
    peak_hr_bpm: float | None
    rmssd_ms: float | None
    sdnn_ms: float | None
    rmssd_delta_vs_baseline_ms: float | None


class RoundImuBlock(BaseModel):
    sample_count: int
    peak_g: float | None
    n_impacts: int
    cv_imu_match_rate: float | None  # what fraction of CV punches had a co-located IMU spike


class RoundExportItem(BaseModel):
    round_number: int
    start_ms: float
    end_ms: float
    duration_ms: float
    rest_after_ms: float
    # Legacy flat fields (kept for the existing dashboard consumer).
    punch_count: int
    peak_velocity_ms: float | None
    ppm: float | None
    events: list[RoundEventOut]
    # Fused per-round blocks — added 2026-05-09 to back RQ1 study.
    cv: RoundCvBlock
    hrv: RoundHrvBlock
    imu: RoundImuBlock


class RoundsExportResponse(BaseModel):
    session_id: UUID
    fighter_id: UUID
    started_at: datetime.datetime
    round_count: int
    round_duration_s: int
    rest_duration_s: int
    study_condition: str | None = None
    rounds: list[RoundExportItem]


@router.get("/{session_id}/rounds_export", response_model=RoundsExportResponse)
def rounds_export(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> RoundsExportResponse:
    from sqlmodel import select as _select

    from store import HRSampleRow, IMUSampleRow

    row = sessions.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")

    rounds_n = row.round_count or 3
    round_s = row.round_duration_s or 180  # default 3-minute boxing round
    rest_s = row.rest_duration_s if row.rest_duration_s is not None else 60  # default 1-min rest
    # The frontend pauses capture during rest periods, so recorded t_ms
    # values are contiguous — no rest gaps in the timeline. Each round
    # occupies exactly round_s of captured time back-to-back.
    round_ms = round_s * 1000.0

    all_events = events.list_for_session(session_id)
    hr_samples = list(
        db.exec(_select(HRSampleRow).where(HRSampleRow.session_id == session_id)).all()
    )
    imu_samples = list(
        db.exec(_select(IMUSampleRow).where(IMUSampleRow.session_id == session_id)).all()
    )

    items: list[RoundExportItem] = []
    for i in range(rounds_n):
        start = i * round_ms
        end = start + round_ms
        round_events = [
            RoundEventOut(
                t_ms=e.t_ms,
                hand=e.hand.value if hasattr(e.hand, "value") else str(e.hand),
                velocity_ms=e.velocity_ms,
                confidence=getattr(e, "confidence", None),
            )
            for e in all_events
            if start <= e.t_ms < end
        ]
        peak = max((e.velocity_ms for e in round_events), default=None)
        ppm = (len(round_events) / (round_s / 60.0)) if round_s > 0 else None

        # HRV block
        hr_in_round = [s for s in hr_samples if start <= s.t_ms < end]
        mean_hr: float | None = None
        peak_hr: float | None = None
        rmssd: float | None = None
        sdnn: float | None = None
        rmssd_delta: float | None = None
        if hr_in_round:
            hrs = [s.hr_bpm for s in hr_in_round]
            rrs = [s.rr_ms for s in hr_in_round]
            mean_hr = sum(hrs) / len(hrs)
            peak_hr = max(hrs)
            # RMSSD over the round window.
            diffs = [rrs[k] - rrs[k - 1] for k in range(1, len(rrs))]
            rmssd = math.sqrt(sum(d * d for d in diffs) / len(diffs)) if diffs else None
            # SDNN — standard deviation of RR intervals in the round.
            if len(rrs) >= 2:
                rr_mean = sum(rrs) / len(rrs)
                sdnn = math.sqrt(sum((r - rr_mean) ** 2 for r in rrs) / (len(rrs) - 1))
            rmssd_delta = (
                rmssd - row.baseline_rmssd_ms
                if rmssd is not None and row.baseline_rmssd_ms is not None
                else None
            )
        hrv_block = RoundHrvBlock(
            sample_count=len(hr_in_round),
            mean_hr_bpm=round(mean_hr, 1) if mean_hr is not None else None,
            peak_hr_bpm=round(peak_hr, 1) if peak_hr is not None else None,
            rmssd_ms=round(rmssd, 1) if rmssd is not None else None,
            sdnn_ms=round(sdnn, 1) if sdnn is not None else None,
            rmssd_delta_vs_baseline_ms=(round(rmssd_delta, 1) if rmssd_delta is not None else None),
        )

        # IMU block — peak |a| in round window, count of impact spikes,
        # match rate vs CV punches (within ±60 ms).
        imu_in_round = [s for s in imu_samples if start <= s.t_ms < end]
        peak_g_val: float | None = None
        n_impacts = 0
        match_rate: float | None = None
        if imu_in_round:
            mags = [
                math.sqrt(s.ax_g * s.ax_g + s.ay_g * s.ay_g + s.az_g * s.az_g) for s in imu_in_round
            ]
            peak_g_val = round(max(mags), 2)
            # Impact = local peak above 3 g. Cheap threshold counter:
            n_impacts = sum(1 for m in mags if m > 3.0)
            if round_events:
                matched = 0
                for ev in round_events:
                    if any(
                        abs(s.t_ms - ev.t_ms) <= 60.0
                        and math.sqrt(s.ax_g * s.ax_g + s.ay_g * s.ay_g + s.az_g * s.az_g) > 2.5
                        for s in imu_in_round
                    ):
                        matched += 1
                match_rate = round(matched / len(round_events), 2)
        imu_block = RoundImuBlock(
            sample_count=len(imu_in_round),
            peak_g=peak_g_val,
            n_impacts=n_impacts,
            cv_imu_match_rate=match_rate,
        )

        cv_block = RoundCvBlock(
            punch_count=len(round_events),
            peak_velocity_ms=peak,
            ppm=ppm,
            events=round_events,
        )
        items.append(
            RoundExportItem(
                round_number=i + 1,
                start_ms=start,
                end_ms=end,
                duration_ms=round_ms,
                rest_after_ms=rest_s * 1000.0 if i < rounds_n - 1 else 0.0,
                punch_count=len(round_events),
                peak_velocity_ms=peak,
                ppm=ppm,
                events=round_events,
                cv=cv_block,
                hrv=hrv_block,
                imu=imu_block,
            )
        )

    return RoundsExportResponse(
        session_id=session_id,
        fighter_id=row.fighter_id,
        started_at=row.started_at,
        round_count=rounds_n,
        round_duration_s=round_s,
        rest_duration_s=rest_s,
        study_condition=row.study_condition,
        rounds=items,
    )


# ---------------------------------------------------------------------------
# Offline reconciliation — run a second-pass detector on the saved pose
# parquet, reconcile with the live punch_event rows, persist the
# consensus stream. The dashboard surfaces the consensus count next to
# the live count; downstream consumers (rounds_export, advice) can
# prefer the consensus rows for higher precision.
# ---------------------------------------------------------------------------


class ReprocessResponse(BaseModel):
    session_id: UUID
    second_pass_name: str
    live_count: int
    offline_count: int
    consensus_count: int
    live_only: int
    offline_only: int


@router.post("/{session_id}/reprocess_offline", response_model=ReprocessResponse)
def reprocess_offline(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> ReprocessResponse:
    from analyze import default_second_pass, reconcile_events
    from contracts import Landmark, PoseFrame, WorldLandmark
    from store import (
        ConsensusEventRepo as _ConsensusEventRepo,
    )
    from store import (
        ConsensusEventRow,
        ConsensusKindEnum,
        HandEnum,
        PunchTypeEnum,
    )

    row = sessions.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not row.pose_parquet_path:
        raise HTTPException(status_code=400, detail="no pose parquet for this session")
    parquet = Path(row.pose_parquet_path)
    if not parquet.exists():
        raise HTTPException(status_code=410, detail=f"parquet missing on disk: {parquet}")

    try:
        import pyarrow.parquet as pq
    except ImportError as e:
        raise HTTPException(status_code=503, detail=f"pyarrow not available: {e}") from e

    table = pq.read_table(parquet)  # type: ignore[no-untyped-call]
    rows_dict = table.to_pylist()

    def _f(d: dict[str, Any], key: str) -> float:
        return float(d[key])  # cast Any → float for mypy

    def _i(d: dict[str, Any], key: str) -> int:
        return int(d[key])

    # Replay parquet rows into PoseFrame. Schema: lm00..lm32 (x,y,z,v) +
    # wl00..wl32 (x,y,z,v).
    def _to_pose_frame(d: dict[str, Any]) -> PoseFrame:
        lm = tuple(
            Landmark(
                x=_f(d, f"lm{i:02d}_x"),
                y=_f(d, f"lm{i:02d}_y"),
                z=_f(d, f"lm{i:02d}_z"),
                visibility=_f(d, f"lm{i:02d}_v"),
            )
            for i in range(33)
        )
        wl: tuple[WorldLandmark, ...] | None = None
        if f"wl{0:02d}_x" in d:
            wl = tuple(
                WorldLandmark(
                    x=_f(d, f"wl{i:02d}_x"),
                    y=_f(d, f"wl{i:02d}_y"),
                    z=_f(d, f"wl{i:02d}_z"),
                    visibility=_f(d, f"wl{i:02d}_v"),
                )
                for i in range(33)
            )
        return PoseFrame(
            session_id=session_id,
            frame_index=_i(d, "frame_index"),
            t_ms=_f(d, "t_ms"),
            landmarks=lm,
            world_landmarks=wl,
        )

    pose_frames = [_to_pose_frame(d) for d in rows_dict]

    # Lookup the fighter's stance so the second-pass labels lead/rear.
    from store import FighterRepo as _FighterRepo

    fighter = _FighterRepo(db).get(row.fighter_id)
    stance_str = fighter.stance.value if fighter else None

    second_pass = default_second_pass()
    offline_events = second_pass.detect(pose_frames, stance=stance_str)

    live_events = [
        # Re-wrap PunchEventRow → PunchEvent contract for reconcile().
        # Only fields the reconciler needs are populated.
        _row_to_event(e)
        for e in events.list_for_session(session_id)
    ]

    consensus = reconcile_events(
        live=live_events,
        offline=offline_events,
        live_label="live",
        offline_label=second_pass.name,
    )

    consensus_rows = [
        ConsensusEventRow(
            session_id=session_id,
            t_ms=c.t_ms,
            hand=HandEnum(c.hand),
            velocity_ms=c.velocity_ms,
            punch_type=PunchTypeEnum(c.punch_type) if c.punch_type else None,
            confidence=c.confidence,
            kind=ConsensusKindEnum(c.kind),
            sources=",".join(c.sources),
            second_pass_name=second_pass.name,
        )
        for c in consensus
    ]
    _ConsensusEventRepo(db).replace_for_session(session_id, consensus_rows)

    return ReprocessResponse(
        session_id=session_id,
        second_pass_name=second_pass.name,
        live_count=len(live_events),
        offline_count=len(offline_events),
        consensus_count=sum(1 for c in consensus if c.kind == "consensus"),
        live_only=sum(1 for c in consensus if c.kind == "live_only"),
        offline_only=sum(1 for c in consensus if c.kind == "offline_only"),
    )


def _row_to_event(e: Any) -> Any:
    """PunchEventRow → contracts.PunchEvent for the reconciler.

    Returns Any deliberately — the row's enum-shaped fields don't
    statically prove they're the exact `Literal[...]` types PunchEvent
    requires, so we strip the type at the boundary and rely on the
    DB-level enum constraints to enforce values.
    """
    from typing import cast as _cast

    from contracts import PunchEvent

    hand_str = e.hand.value if hasattr(e.hand, "value") else str(e.hand)
    lead_or_rear_str = (
        e.lead_or_rear.value if e.lead_or_rear and hasattr(e.lead_or_rear, "value") else None
    )
    velocity_source_str = (
        e.velocity_source.value if hasattr(e.velocity_source, "value") else str(e.velocity_source)
    )
    punch_type_str = e.punch_type.value if e.punch_type and hasattr(e.punch_type, "value") else None
    detected_by_str = e.detected_by.value if hasattr(e.detected_by, "value") else str(e.detected_by)
    return PunchEvent(
        session_id=e.session_id,
        t_ms=e.t_ms,
        hand=_cast(Any, hand_str),
        lead_or_rear=_cast(Any, lead_or_rear_str),
        velocity_ms=e.velocity_ms,
        velocity_source=_cast(Any, velocity_source_str),
        punch_type=_cast(Any, punch_type_str),
        detected_by=_cast(Any, detected_by_str),
        confidence=float(e.confidence),
    )


@router.get(
    "/{session_id}/consensus_events",
    response_model=list[dict[str, Any]],
)
def list_consensus_events(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> list[dict[str, Any]]:
    """Read-only view of the reconciled consensus stream."""
    from store import ConsensusEventRepo as _ConsensusEventRepo

    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    rows = _ConsensusEventRepo(db).list_for_session(session_id)
    return [
        {
            "t_ms": r.t_ms,
            "hand": r.hand.value if hasattr(r.hand, "value") else str(r.hand),
            "velocity_ms": r.velocity_ms,
            "punch_type": (
                r.punch_type.value if r.punch_type and hasattr(r.punch_type, "value") else None
            ),
            "confidence": r.confidence,
            "kind": r.kind.value if hasattr(r.kind, "value") else str(r.kind),
            "sources": r.sources,
            "second_pass_name": r.second_pass_name,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Detector evaluation — manual labels vs detector output
# ---------------------------------------------------------------------------


def _labels_path(session_id: UUID) -> Path:
    base = Path("data/labels")
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{session_id}.json"


class GroundTruthPunchIn(BaseModel):
    t_ms: float
    hand: str  # "left" | "right"
    punch_type: str | None = None  # "jab" | "cross" | "hook" | "uppercut" | None


class LabelsPayload(BaseModel):
    labels: list[GroundTruthPunchIn]


class EvalResponse(BaseModel):
    session_id: UUID
    has_labels: bool
    label_count: int
    detection_count: int
    tolerance_ms: float = 200.0
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    precision: float = 0.0
    recall: float = 0.0
    f1: float = 0.0
    mean_temporal_offset_ms: float = 0.0
    confusion: dict[str, dict[str, int]] | None = None
    classes: list[str] = []


@router.get("/{session_id}/labels", response_model=LabelsPayload | None)
def get_labels(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
) -> LabelsPayload | None:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    path = _labels_path(session_id)
    if not path.exists():
        return None
    import json

    raw = json.loads(path.read_text())
    return LabelsPayload(labels=raw)


@router.put("/{session_id}/labels", response_model=LabelsPayload)
def put_labels(
    session_id: UUID,
    payload: LabelsPayload,
    repo: SessionRepo = Depends(session_repo),
) -> LabelsPayload:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    import json

    body = [lab.model_dump() for lab in payload.labels]
    _labels_path(session_id).write_text(json.dumps(body, indent=2))
    return payload


@router.delete("/{session_id}/labels", status_code=status.HTTP_204_NO_CONTENT)
def delete_labels(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
) -> None:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    p = _labels_path(session_id)
    if p.exists():
        p.unlink()


@router.get("/{session_id}/evaluation", response_model=EvalResponse)
def session_evaluation(
    session_id: UUID,
    tolerance_ms: float = 200.0,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
) -> EvalResponse:
    """Compare manual labels against detector output for this session.

    The dissertation's defensible accuracy claim hinges on this number.
    Returns zeroed metrics when no labels file exists for the session.
    """
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")

    detection_rows = events.list_for_session(session_id)
    detected = [
        DetectedPunch(
            t_ms=r.t_ms,
            hand=r.hand.value,
            punch_type=r.punch_type.value if r.punch_type else None,
            confidence=r.confidence,
        )
        for r in detection_rows
    ]

    label_path = _labels_path(session_id)
    if not label_path.exists():
        return EvalResponse(
            session_id=session_id,
            has_labels=False,
            label_count=0,
            detection_count=len(detected),
            tolerance_ms=tolerance_ms,
        )

    truth = load_labels(label_path)
    result = match_events(truth, detected, tolerance_ms=tolerance_ms)
    classes = ["jab", "cross", "hook", "uppercut"]
    cm = confusion_matrix(result.pairs, classes)
    return EvalResponse(
        session_id=session_id,
        has_labels=True,
        label_count=len(truth),
        detection_count=len(detected),
        tolerance_ms=tolerance_ms,
        true_positives=result.true_positives,
        false_positives=result.false_positives,
        false_negatives=result.false_negatives,
        precision=round(result.precision, 4),
        recall=round(result.recall, 4),
        f1=round(result.f1, 4),
        mean_temporal_offset_ms=round(result.mean_temporal_offset_ms, 1),
        confusion=cm,
        classes=classes,
    )


# ---------------------------------------------------------------------------
# Session attachments — arbitrary files (extra videos, sparring photos,
# coach notes PDFs, etc.) hung off a session for reference.
# ---------------------------------------------------------------------------


_ATTACHMENT_DIR = Path("data/raw/attachments")
_ATTACHMENT_MAX_BYTES = 200 * 1024 * 1024  # 200 MB


def _classify_kind(mime: str | None, filename: str) -> AttachmentKind:
    if mime:
        m = mime.lower()
        if m.startswith("video/"):
            return AttachmentKind.VIDEO
        if m.startswith("image/"):
            return AttachmentKind.IMAGE
        if m.startswith("audio/"):
            return AttachmentKind.AUDIO
        if m in ("application/pdf",) or m.startswith("text/"):
            return AttachmentKind.DOCUMENT
    ext = Path(filename).suffix.lower()
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return AttachmentKind.VIDEO
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return AttachmentKind.IMAGE
    if ext in {".mp3", ".wav", ".m4a", ".ogg"}:
        return AttachmentKind.AUDIO
    if ext in {".pdf", ".txt", ".md", ".doc", ".docx"}:
        return AttachmentKind.DOCUMENT
    return AttachmentKind.OTHER


@router.get("/{session_id}/attachments", response_model=list[SessionAttachmentRead])
def list_attachments(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> list[SessionAttachmentRead]:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    from sqlmodel import select

    rows = list(
        db.exec(select(SessionAttachment).where(SessionAttachment.session_id == session_id)).all()
    )
    rows.sort(key=lambda a: a.uploaded_at, reverse=True)
    return [SessionAttachmentRead.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/{session_id}/attachments",
    response_model=SessionAttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    session_id: UUID,
    file: UploadFile = File(...),
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> SessionAttachmentRead:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(body) > _ATTACHMENT_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=(f"file too large ({len(body)} bytes; max {_ATTACHMENT_MAX_BYTES})"),
        )
    out_dir = _ATTACHMENT_DIR / str(session_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = file.filename or "unnamed"
    dest = out_dir / fname
    # Avoid clobbering: if a file with the same name exists, append a counter.
    if dest.exists():
        stem = dest.stem
        ext = dest.suffix
        i = 1
        while (out_dir / f"{stem} ({i}){ext}").exists():
            i += 1
        dest = out_dir / f"{stem} ({i}){ext}"
    dest.write_bytes(body)
    row = SessionAttachment(
        session_id=session_id,
        filename=dest.name,
        path=str(dest),
        mime_type=file.content_type,
        size_bytes=len(body),
        kind=_classify_kind(file.content_type, fname),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return SessionAttachmentRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{session_id}/attachments/{attachment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    session_id: UUID,
    attachment_id: int,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> None:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    row = db.get(SessionAttachment, attachment_id)
    if row is None or row.session_id != session_id:
        raise HTTPException(status_code=404, detail="attachment not found")
    try:
        Path(row.path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(row)
    db.commit()

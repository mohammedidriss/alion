"""Session CRUD + capture orchestration."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from api.deps import db_session, punch_event_repo, session_repo
from api.services import capture_runner
from store import (
    PunchEventRepo,
    SessionRepo,
    SessionSourceEnum,
    SessionStatus,
)
from store.models import (
    PunchEventRead,
    SessionCreate,
    SessionRead,
)

router = APIRouter(prefix="/sessions", tags=["sessions"])

_VIDEO_DIR = Path("data/raw/uploaded")


class CaptureStartRequest(BaseModel):
    max_frames: int | None = None


class CaptureStatusResponse(BaseModel):
    session_id: UUID
    status: SessionStatus
    is_running: bool
    frame_count: int
    duration_ms: float
    punch_count: int


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
def create_session(data: SessionCreate, repo: SessionRepo = Depends(session_repo)) -> SessionRead:
    row = repo.create(data)
    return SessionRead.model_validate(row, from_attributes=True)


@router.get("", response_model=list[SessionRead])
def list_sessions(repo: SessionRepo = Depends(session_repo)) -> list[SessionRead]:
    return [SessionRead.model_validate(s, from_attributes=True) for s in repo.list_all()]


@router.get("/{session_id}", response_model=SessionRead)
def get_session_route(session_id: UUID, repo: SessionRepo = Depends(session_repo)) -> SessionRead:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionRead.model_validate(row, from_attributes=True)


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

    started = capture_runner.start_capture(
        session_id,
        row.source.value,
        factory,
        video_path=row.video_path,
        max_frames=body.max_frames if body else None,
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
        frame_count=row.frame_count,
        duration_ms=row.duration_ms,
        punch_count=events.count_for_session(session_id),
    )


@router.get("/{session_id}/events", response_model=list[PunchEventRead])
def list_events(
    session_id: UUID, events: PunchEventRepo = Depends(punch_event_repo)
) -> list[PunchEventRead]:
    rows = events.list_for_session(session_id)
    return [PunchEventRead.model_validate(r, from_attributes=True) for r in rows]

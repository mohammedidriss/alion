"""HRV stream endpoints — upload an RR CSV, start replay, list samples + metrics."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlmodel import Session as DBSession
from sqlmodel import select

from api.deps import db_session, session_repo
from api.services import hrv_runner
from contracts import HRMetricsWindow
from store import HRSampleRead, HRSampleRow, SessionRepo
from store.models import SessionRead

router = APIRouter(prefix="/sessions", tags=["hrv"])

_HRV_DIR = Path("data/raw/hrv")


class HrvStartRequest(BaseModel):
    realtime: bool = False
    window_ms: float = 60_000.0


class HrvStatusResponse(BaseModel):
    session_id: UUID
    is_running: bool
    sample_count: int
    metrics: HRMetricsWindow | None = None


@router.post("/{session_id}/hrv/upload", response_model=SessionRead, tags=["hrv"])
def upload_hrv_csv(
    session_id: UUID,
    file: UploadFile = File(...),
    repo: SessionRepo = Depends(session_repo),
) -> SessionRead:
    """Upload an RR-interval CSV (single-column rr_ms or two-column t_ms,rr_ms).

    Stores it under data/raw/hrv/{session_id}.csv and pins the path on the
    Session row's `notes` field so the runner can find it. Once we have a
    Session.hrv_csv_path column we'll move it there cleanly.
    """
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    _HRV_DIR.mkdir(parents=True, exist_ok=True)
    dest = _HRV_DIR / f"{session_id}.csv"
    with dest.open("wb") as out:
        while chunk := file.file.read(1024 * 1024):
            out.write(chunk)
    # Stamp the path into notes (Phase-1-friendly, no schema change required).
    note_marker = f"hrv_csv: {dest}"
    new_notes = note_marker if not row.notes else f"{row.notes}\n{note_marker}"
    updated = repo.attach_artifacts(session_id)  # no-op refresh
    if updated is not None:
        updated.notes = new_notes
    # Set notes through SessionRepo via a direct update.
    row.notes = new_notes
    return SessionRead.model_validate(row, from_attributes=True)


@router.post("/{session_id}/hrv/start", response_model=HrvStatusResponse, tags=["hrv"])
def start_hrv_replay(
    session_id: UUID,
    body: HrvStartRequest | None = None,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> HrvStatusResponse:
    row = repo.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if hrv_runner.is_running(session_id):
        raise HTTPException(status_code=409, detail="hrv replay already running")

    csv_path = _HRV_DIR / f"{session_id}.csv"
    if not csv_path.exists():
        raise HTTPException(status_code=400, detail="upload an HRV CSV first")

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

    started = hrv_runner.start_replay(
        session_id,
        csv_path,
        factory,
        realtime=body.realtime if body else False,
        window_ms=body.window_ms if body else 60_000.0,
    )
    if not started:
        raise HTTPException(status_code=409, detail="hrv replay already running")

    return HrvStatusResponse(
        session_id=session_id,
        is_running=True,
        sample_count=_count_samples(db, session_id),
        metrics=None,
    )


@router.post("/{session_id}/hrv/stop", response_model=HrvStatusResponse, tags=["hrv"])
def stop_hrv(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> HrvStatusResponse:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not hrv_runner.request_stop(session_id):
        raise HTTPException(status_code=409, detail="no hrv replay running")
    return HrvStatusResponse(
        session_id=session_id,
        is_running=True,  # actual stop happens on next sample boundary
        sample_count=_count_samples(db, session_id),
        metrics=hrv_runner.latest_metrics(session_id),
    )


@router.get("/{session_id}/hrv/samples", response_model=list[HRSampleRead], tags=["hrv"])
def list_hrv_samples(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
    limit: int | None = None,
) -> list[HRSampleRead]:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    stmt = (
        select(HRSampleRow).where(HRSampleRow.session_id == session_id).order_by(HRSampleRow.t_ms)  # type: ignore[arg-type]
    )
    if limit is not None and limit > 0:
        stmt = stmt.limit(limit)
    rows = list(db.exec(stmt).all())
    return [HRSampleRead.model_validate(r, from_attributes=True) for r in rows]


@router.get("/{session_id}/hrv/metrics", response_model=HRMetricsWindow | None, tags=["hrv"])
def hrv_current_metrics(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
) -> HRMetricsWindow | None:
    """Most recent rolling-window summary. Returns null if no samples yet."""
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return hrv_runner.latest_metrics(session_id)


@router.get("/{session_id}/hrv/status", response_model=HrvStatusResponse, tags=["hrv"])
def hrv_status(
    session_id: UUID,
    repo: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> HrvStatusResponse:
    if repo.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return HrvStatusResponse(
        session_id=session_id,
        is_running=hrv_runner.is_running(session_id),
        sample_count=_count_samples(db, session_id),
        metrics=hrv_runner.latest_metrics(session_id),
    )


def _count_samples(db: DBSession, session_id: UUID) -> int:
    rows = db.exec(select(HRSampleRow).where(HRSampleRow.session_id == session_id)).all()
    return len(list(rows))

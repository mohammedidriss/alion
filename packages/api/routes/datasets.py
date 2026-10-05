"""Datasets API (ADR-013) — datasets, participants' consent, and recorded takes.

A take is recorded with the same engines as a training session (camera
coordinator, wrist-IMU recorder, Polar stream) but everything it captures lands
in its own folder (`dataset_store`), never in session tables. Its routes mirror a
session's, under `/takes/{id}` instead of `/sessions/{id}`:

- `/v2/datasets…`, `/v2/takes/{id}`            — datasets, participants, takes
- `/takes/{id}/multicam/join-info|complete`    — the take-specific capture steps
  (device / start / stop / upload routes are shared: `capture_coord.take_*`)
- `/v2/takes/{id}/imu/ble/*`, `/hrv/*`, `/live` — sensors and the live reader
"""

from __future__ import annotations

import shutil
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from api.deps import db_session, fighter_repo
from api.routes import capture_coord
from api.routes.auth import require_current_user
from api.routes.capture_coord import JoinInfo
from api.routes.imu_ble import ImuBleStatus, session_status
from api.routes.live import LiveHeart, LiveOut, hr_zone, max_hr_for
from api.services import dataset_store, hrv_runner, imu_devices, imu_runner
from store import (
    DatasetCreate,
    DatasetParticipantIn,
    DatasetRead,
    DatasetRepo,
    DatasetTake,
    FighterRepo,
    TakeStatusEnum,
)

_auth = [Depends(require_current_user)]
router = APIRouter(prefix="/v2", tags=["datasets"], dependencies=_auth)
capture = APIRouter(prefix="/takes", tags=["datasets"], dependencies=_auth)


def dataset_repo(db: DBSession = Depends(db_session)) -> DatasetRepo:
    return DatasetRepo(db)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class ParticipantOut(BaseModel):
    fighter_id: UUID
    name: str
    stance: str | None = None
    consent: str
    may_record: bool
    consent_date: str | None = None
    irb_ref: str | None = None
    notes: str | None = None
    takes: int = 0


class TakeOut(BaseModel):
    id: UUID
    dataset_id: UUID
    dataset_name: str | None = None
    fighter_id: UUID
    fighter_name: str | None = None
    status: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: float
    notes: str | None = None
    data: dict[str, Any] = {}  # dataset_store.summary(): clips, imu/hr rows, labels


class DatasetSummary(DatasetRead):
    participants: int = 0
    takes: int = 0
    completed_takes: int = 0


class DatasetOut(DatasetRead):
    participants: list[ParticipantOut]
    takes: list[TakeOut]


class TakeCreate(BaseModel):
    fighter_id: UUID


class CompleteBody(BaseModel):
    duration_ms: float | None = None


class HrStartBody(BaseModel):
    address: str
    window_ms: float = 60_000.0


class HrStatusOut(BaseModel):
    session_id: UUID  # the take id — same shape as a session's HRV status
    is_running: bool
    sample_count: int = 0


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------


def _take_out(take: DatasetTake, fighters: FighterRepo, dataset_name: str | None) -> TakeOut:
    fighter = fighters.get(take.fighter_id)
    folder = dataset_store.take_dir(take.id)
    return TakeOut(
        id=take.id,
        dataset_id=take.dataset_id,
        dataset_name=dataset_name,
        fighter_id=take.fighter_id,
        fighter_name=fighter.name if fighter else None,
        status=str(take.status),
        started_at=take.started_at,
        ended_at=take.ended_at,
        duration_ms=take.duration_ms,
        notes=take.notes,
        data=dataset_store.summary(folder) if folder else {},
    )


def _get_take(take_id: UUID, repo: DatasetRepo) -> DatasetTake:
    take = repo.get_take(take_id)
    if take is None:
        raise HTTPException(status_code=404, detail="take not found")
    return take


def _folder(take_id: UUID) -> Any:
    folder = dataset_store.take_dir(take_id)
    if folder is None:
        raise HTTPException(status_code=404, detail="take folder missing on disk")
    return folder


def _release_capture(take_id: UUID, *, cameras: bool = False, discard: bool = False) -> None:
    """Free the wrist sensors and the Polar a take was using, so the next take can
    connect. `cameras` also stops its cameras (they upload); `discard` makes them
    drop the clip instead."""
    imu_runner.stop(take_id)
    hrv_runner.request_stop(take_id)
    if discard:
        capture_coord.discard_capture(take_id)
    elif cameras:
        capture_coord.stop_capture(take_id)


def _require_recording(take: DatasetTake) -> None:
    if take.status != TakeStatusEnum.RECORDING:
        raise HTTPException(status_code=409, detail=f"take is {take.status} — record a new take")


# --------------------------------------------------------------------------
# Datasets + participants
# --------------------------------------------------------------------------


@router.get("/datasets", response_model=list[DatasetSummary])
def list_datasets(repo: DatasetRepo = Depends(dataset_repo)) -> list[DatasetSummary]:
    out = []
    for d in repo.list_all():
        takes = repo.takes(d.id)
        out.append(
            DatasetSummary(
                **DatasetRead.model_validate(d, from_attributes=True).model_dump(),
                participants=len(repo.participants(d.id)),
                takes=len([t for t in takes if t.status != TakeStatusEnum.DISCARDED]),
                completed_takes=len([t for t in takes if t.status == TakeStatusEnum.COMPLETED]),
            )
        )
    return out


@router.post("/datasets", response_model=DatasetRead, status_code=201)
def create_dataset(body: DatasetCreate, repo: DatasetRepo = Depends(dataset_repo)) -> DatasetRead:
    row = repo.create(body)
    dataset_store.dataset_dir(row.id).mkdir(parents=True, exist_ok=True)
    return DatasetRead.model_validate(row, from_attributes=True)


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(
    dataset_id: UUID,
    repo: DatasetRepo = Depends(dataset_repo),
    fighters: FighterRepo = Depends(fighter_repo),
) -> DatasetOut:
    d = repo.get(dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    takes = repo.takes(dataset_id)
    participants = []
    for p in repo.participants(dataset_id):
        f = fighters.get(p.fighter_id)
        participants.append(
            ParticipantOut(
                fighter_id=p.fighter_id,
                name=f.name if f else "(deleted fighter)",
                stance=str(f.stance) if f and f.stance else None,
                consent=str(p.consent),
                may_record=p.consent in ("self", "irb_signed"),
                consent_date=p.consent_date.isoformat() if p.consent_date else None,
                irb_ref=p.irb_ref,
                notes=p.notes,
                takes=len(
                    [
                        t
                        for t in takes
                        if t.fighter_id == p.fighter_id and t.status == TakeStatusEnum.COMPLETED
                    ]
                ),
            )
        )
    return DatasetOut(
        **DatasetRead.model_validate(d, from_attributes=True).model_dump(),
        participants=participants,
        takes=[_take_out(t, fighters, d.name) for t in takes],
    )


@router.put("/datasets/{dataset_id}/participants", response_model=DatasetOut)
def set_participant(
    dataset_id: UUID,
    body: DatasetParticipantIn,
    repo: DatasetRepo = Depends(dataset_repo),
    fighters: FighterRepo = Depends(fighter_repo),
) -> DatasetOut:
    """Add a fighter to the dataset, or change their consent."""
    if repo.get(dataset_id) is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    try:
        repo.set_participant(dataset_id, body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return get_dataset(dataset_id, repo, fighters)


# --------------------------------------------------------------------------
# Takes
# --------------------------------------------------------------------------


@router.post("/datasets/{dataset_id}/takes", response_model=TakeOut, status_code=201)
def create_take(
    dataset_id: UUID,
    body: TakeCreate,
    repo: DatasetRepo = Depends(dataset_repo),
    fighters: FighterRepo = Depends(fighter_repo),
) -> TakeOut:
    """Start a new take for a participant — refused unless their consent allows it."""
    d = repo.get(dataset_id)
    if d is None:
        raise HTTPException(status_code=404, detail="dataset not found")
    try:
        take = repo.create_take(dataset_id, body.fighter_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    fighter = fighters.get(take.fighter_id)
    dataset_store.create_take_dir(
        dataset_id,
        take.id,
        {
            "take_id": str(take.id),
            "dataset_id": str(dataset_id),
            "dataset": d.name,
            "protocol": d.protocol,
            "fighter_id": str(take.fighter_id),
            "fighter": fighter.name if fighter else None,
            "stance": str(fighter.stance) if fighter and fighter.stance else None,
            "status": "recording",
            "created_at": take.started_at.isoformat(),
            "timeline": "t_ms = ms since the cameras' synchronized start (t0_ms, server "
            "wall clock); takes are never paused",
            "t0_ms": None,
            "duration_ms": None,
            "devices": [],
        },
    )
    return _take_out(take, fighters, d.name)


@router.get("/takes/{take_id}", response_model=TakeOut)
def get_take(
    take_id: UUID,
    repo: DatasetRepo = Depends(dataset_repo),
    fighters: FighterRepo = Depends(fighter_repo),
) -> TakeOut:
    take = _get_take(take_id, repo)
    d = repo.get(take.dataset_id)
    return _take_out(take, fighters, d.name if d else None)


@router.delete("/takes/{take_id}", status_code=204)
def delete_take(take_id: UUID, repo: DatasetRepo = Depends(dataset_repo)) -> None:
    """Delete a take for good — the coach's "Delete" on a recording that went wrong:
    the cameras drop their clips, the sensors stop, and the row and folder go."""
    take = _get_take(take_id, repo)
    _release_capture(take_id, discard=True)
    folder = dataset_store.take_dir(take_id)
    if folder is not None:
        shutil.rmtree(folder, ignore_errors=True)
    repo.delete_take(take.id)


@router.post("/takes/{take_id}/discard", response_model=TakeOut)
def discard_take(
    take_id: UUID,
    repo: DatasetRepo = Depends(dataset_repo),
    fighters: FighterRepo = Depends(fighter_repo),
) -> TakeOut:
    """Exclude a take from the dataset. Its files stay on disk. Anything still
    recording into it stops — sensors, Polar and the cameras."""
    take = _get_take(take_id, repo)
    _release_capture(take_id, cameras=True)
    repo.finish_take(take.id, TakeStatusEnum.DISCARDED)
    folder = dataset_store.take_dir(take_id)
    if folder is not None:
        dataset_store.update_take_json(folder, status="discarded")
    return get_take(take_id, repo, fighters)


# --------------------------------------------------------------------------
# Capture — the take-specific steps (shared device/start/stop routes live in
# capture_coord.take_master / take_slave)
# --------------------------------------------------------------------------


@capture.post("/{take_id}/multicam/join-info", response_model=JoinInfo)
def take_join_info(take_id: UUID, repo: DatasetRepo = Depends(dataset_repo)) -> JoinInfo:
    take = _get_take(take_id, repo)
    _require_recording(take)
    _folder(take_id)
    return capture_coord.join(take_id, "/takes")


@capture.post("/{take_id}/multicam/complete", response_model=dict)
def take_complete(
    take_id: UUID, body: CompleteBody, repo: DatasetRepo = Depends(dataset_repo)
) -> dict[str, object]:
    """Stop's clips have landed: record the devices and timing, mark it completed."""
    take = _get_take(take_id, repo)
    folder = _folder(take_id)
    clips = dataset_store.clips(folder)
    if not clips:
        raise HTTPException(status_code=409, detail="no video was saved for this take")
    dataset_store.update_take_json(
        folder,
        status="completed",
        t0_ms=capture_coord.last_started_at_ms(take_id),
        duration_ms=body.duration_ms,
        ended_at=datetime.now(UTC).isoformat(),
        devices=clips,
    )
    repo.finish_take(take.id, TakeStatusEnum.COMPLETED, body.duration_ms)
    _release_capture(take_id)  # the client stops them too; this makes sure
    return {"status": "completed", "clips": len(clips)}


# --------------------------------------------------------------------------
# Sensors + live reader
# --------------------------------------------------------------------------


@router.post("/takes/{take_id}/imu/ble/start", response_model=ImuBleStatus)
def take_imu_start(
    take_id: UUID, arm: bool = False, repo: DatasetRepo = Depends(dataset_repo)
) -> ImuBleStatus:
    """Stream both wrists into the take. `arm`: connect before the cameras start and
    store from their t = 0 (the coordinator sets it at Start)."""
    take = _get_take(take_id, repo)
    _require_recording(take)
    folder = _folder(take_id)
    units = imu_devices.units_by_hand()
    if not units:
        raise HTTPException(
            status_code=409,
            detail="No IMU units configured — run scripts/imu_tool.py assign first.",
        )
    if imu_devices.owner_id() != str(take.fighter_id):
        raise HTTPException(
            status_code=409, detail="The IMU sensors aren't assigned to this fighter."
        )
    if not imu_runner.is_running(take_id):
        t0 = capture_coord.started_at_ms(take_id) or (
            imu_runner.ARMED if arm else time.time() * 1000.0
        )
        imu_runner.start(take_id, units, t0, dataset_store.imu_writer(folder))
    return session_status(take_id)


@router.post("/takes/{take_id}/imu/ble/stop", response_model=ImuBleStatus)
def take_imu_stop(take_id: UUID) -> ImuBleStatus:
    imu_runner.stop(take_id)
    return session_status(take_id)


@router.get("/takes/{take_id}/imu/ble/status", response_model=ImuBleStatus)
def take_imu_status(take_id: UUID) -> ImuBleStatus:
    return session_status(take_id)


@router.post("/takes/{take_id}/hrv/ble/start", response_model=HrStatusOut)
def take_hr_start(
    take_id: UUID, body: HrStartBody, repo: DatasetRepo = Depends(dataset_repo)
) -> HrStatusOut:
    take = _get_take(take_id, repo)
    _require_recording(take)
    folder = _folder(take_id)
    if not hrv_runner.is_running(take_id):
        # Connects whenever asked (often before the cameras start); beats are stored
        # from the cameras' t = 0, stamped by arrival on the take's timeline.
        hrv_runner.start_ble(
            take_id,
            body.address,
            None,
            window_ms=body.window_ms,
            write_rows=dataset_store.hr_writer(
                folder, lambda: capture_coord.last_started_at_ms(take_id)
            ),
            wall_clock=True,
        )
    return HrStatusOut(session_id=take_id, is_running=True)


@router.post("/takes/{take_id}/hrv/stop", response_model=HrStatusOut)
def take_hr_stop(take_id: UUID) -> HrStatusOut:
    hrv_runner.request_stop(take_id)
    return HrStatusOut(session_id=take_id, is_running=False)


@router.get("/takes/{take_id}/live", response_model=LiveOut)
def take_live(
    take_id: UUID,
    repo: DatasetRepo = Depends(dataset_repo),
    fighters: FighterRepo = Depends(fighter_repo),
) -> LiveOut:
    """The live reader for a take: same shape as a session's."""
    take = _get_take(take_id, repo)
    folder = dataset_store.take_dir(take_id)
    # Live beats from the strap (incl. before t = 0, so a pre-connected strap shows),
    # else what the take stored.
    live = hrv_runner.recent_bpm(take_id)
    stored = dataset_store.recent_bpm(folder) if folder else []
    trace = [round(b, 1) for b in (live or stored)]
    metrics = hrv_runner.latest_metrics(take_id)
    fighter = fighters.get(take.fighter_id)
    max_hr = max_hr_for(fighter.dob if fighter else None)
    bpm = trace[-1] if trace else None
    heart = LiveHeart(
        streaming=hrv_runner.is_running(take_id),
        bpm=bpm,
        bpm_trace=trace,
        rmssd_ms=round(metrics.rmssd_ms, 1) if metrics else None,
        max_hr=max_hr,
        zone=hr_zone(bpm, max_hr) if bpm is not None and max_hr else None,
        error=hrv_runner.last_error(take_id),
    )
    return LiveOut(heart=heart, imu=session_status(take_id))

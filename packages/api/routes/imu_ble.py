"""Live wrist IMUs over Bluetooth — the WT901 pair (configured with scripts/imu_tool.py).

Mirrors the Polar H10 BLE flow: the session page shows an "IMU sensors" card,
and the sensors start/stop with the cameras. The pair belongs to one fighter
(set via `PUT /v2/imu/devices/owner`); streaming is only allowed on that
fighter's sessions, so one athlete's wrist data can't land in another's record.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from api.deps import db_session, fighter_repo, session_repo
from api.routes import capture_coord
from api.routes.auth import require_current_user
from api.routes.imu import _check_imu_condition
from api.services import imu_devices, imu_runner
from capture.imu.witmotion import battery_percent
from store import FighterRepo, SessionRepo

devices_router = APIRouter(
    prefix="/imu", tags=["imu"], dependencies=[Depends(require_current_user)]
)
router = APIRouter(prefix="/sessions", tags=["imu"], dependencies=[Depends(require_current_user)])


class ImuUnit(BaseModel):
    hand: str
    address: str
    name: str | None = None


class ImuOwner(BaseModel):
    fighter_id: str
    name: str


class ImuDevicesOut(BaseModel):
    units: list[ImuUnit]
    owner: ImuOwner | None


class ImuOwnerIn(BaseModel):
    fighter_id: UUID


class ImuUnitStatus(BaseModel):
    connected: bool = False
    samples: int = 0
    hz: float = 0.0
    battery_v: float | None = None
    battery_pct: int | None = None
    last_g: float = 0.0
    peak_g: float = 0.0
    error: str | None = None
    trace: list[float] = []  # live: peak |a| per 50 ms, last 5 s (oldest first)


class ImuBleStatus(BaseModel):
    running: bool
    paused: bool = False
    error: str | None = None
    units: dict[str, ImuUnitStatus]


def _devices_out(fighters: FighterRepo) -> ImuDevicesOut:
    units = [
        ImuUnit(hand=str(u["hand"]), address=str(u["address"]), name=u["name"])
        for u in imu_devices.units()
    ]
    owner = None
    oid = imu_devices.owner_id()
    if oid is not None:
        try:
            row = fighters.get(UUID(oid))
        except ValueError:
            row = None
        if row is not None:
            owner = ImuOwner(fighter_id=oid, name=row.name)
    return ImuDevicesOut(units=units, owner=owner)


def _unit_status(u: dict[str, object]) -> ImuUnitStatus:
    st = ImuUnitStatus.model_validate(u)
    if st.battery_v is not None:
        st.battery_pct = battery_percent(st.battery_v)
    return st


def session_status(session_id: UUID) -> ImuBleStatus:
    st = imu_runner.status(session_id)
    if st is None:  # never started: report the configured wrists as idle
        return ImuBleStatus(
            running=False, units={h: ImuUnitStatus() for h in imu_devices.units_by_hand()}
        )
    return ImuBleStatus(
        running=st["running"],
        paused=st["paused"],
        error=st["error"],
        units={h: _unit_status(u) for h, u in st["units"].items()},
    )


@devices_router.get("/devices", response_model=ImuDevicesOut)
def get_devices(fighters: FighterRepo = Depends(fighter_repo)) -> ImuDevicesOut:
    """The configured wrist units and the fighter who wears them."""
    return _devices_out(fighters)


@devices_router.put("/devices/owner", response_model=ImuDevicesOut)
def set_owner(body: ImuOwnerIn, fighters: FighterRepo = Depends(fighter_repo)) -> ImuDevicesOut:
    if not imu_devices.units_by_hand():
        raise HTTPException(
            status_code=409,
            detail="No IMU units configured — run scripts/imu_tool.py assign first.",
        )
    if fighters.get(body.fighter_id) is None:
        raise HTTPException(status_code=404, detail="fighter not found")
    imu_devices.set_owner(str(body.fighter_id))
    return _devices_out(fighters)


@devices_router.put("/devices/swap", response_model=ImuDevicesOut)
def swap_wrists(fighters: FighterRepo = Depends(fighter_repo)) -> ImuDevicesOut:
    """The wrist check found the units on the wrong wrists: swap the assignment.
    A stream already running keeps its old labels — restart it (the take page re-arms)."""
    if len(imu_devices.units_by_hand()) != 2:
        raise HTTPException(status_code=409, detail="Both wrist units must be assigned first.")
    imu_devices.swap_wrists()
    return _devices_out(fighters)


@devices_router.post("/devices/check", response_model=ImuBleStatus)
def check_devices() -> ImuBleStatus:
    """Connect to both wrists for a few seconds — no session, nothing stored — and
    report each one's link, rate and battery. Takes ~5–10 s."""
    units = imu_devices.units_by_hand()
    if not units:
        raise HTTPException(
            status_code=409,
            detail="No IMU units configured — run scripts/imu_tool.py assign first.",
        )
    if imu_runner.any_running():
        raise HTTPException(
            status_code=409,
            detail="The sensors are recording a session right now — check them there.",
        )
    st = imu_runner.check(units)
    return ImuBleStatus(
        running=False,
        error=st["error"],
        units={h: _unit_status(u) for h, u in st["units"].items()},
    )


@router.post("/{session_id}/imu/ble/start", response_model=ImuBleStatus)
def start_imu(
    session_id: UUID,
    arm: bool = False,
    sessions: SessionRepo = Depends(session_repo),
    fighters: FighterRepo = Depends(fighter_repo),
    db: DBSession = Depends(db_session),
) -> ImuBleStatus:
    """Start streaming both wrists into this session (idempotent if already running).

    t = 0 is the cameras' synchronized start, so call this right after
    `/multicam/start`; without an active camera start it falls back to now.
    """
    _check_imu_condition(sessions, session_id)
    session = sessions.get(session_id)
    assert session is not None  # _check_imu_condition 404s otherwise
    units = imu_devices.units_by_hand()
    if not units:
        raise HTTPException(
            status_code=409,
            detail="No IMU units configured — run scripts/imu_tool.py assign first.",
        )
    owner = imu_devices.owner_id()
    if owner is None:
        raise HTTPException(status_code=409, detail="The IMU pair has no owner — assign a fighter.")
    if owner != str(session.fighter_id):
        name = _devices_out(fighters).owner
        raise HTTPException(
            status_code=409,
            detail=f"The IMU sensors are assigned to {name.name if name else 'another fighter'}.",
        )
    if imu_runner.is_running(session_id):
        return session_status(session_id)

    engine = db.get_bind()  # the request's engine — the test DB in tests, the real one live

    @contextmanager
    def factory() -> Iterator[DBSession]:
        with DBSession(engine) as s:
            yield s

    # arm: connect now (live view), store from the cameras' start (set_t0 at Start).
    t0 = capture_coord.started_at_ms(session_id) or (
        imu_runner.ARMED if arm else time.time() * 1000.0
    )
    imu_runner.start(session_id, units, t0, imu_runner.db_writer(factory))
    return session_status(session_id)


@router.post("/{session_id}/imu/ble/stop", response_model=ImuBleStatus)
def stop_imu(session_id: UUID) -> ImuBleStatus:
    imu_runner.stop(session_id)
    return session_status(session_id)


@router.get("/{session_id}/imu/ble/status", response_model=ImuBleStatus)
def imu_status(session_id: UUID) -> ImuBleStatus:
    """Live per-wrist status: connected, rate, samples stored, battery, last/peak g."""
    return session_status(session_id)

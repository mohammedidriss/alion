"""Synchronized multi-device capture coordinator — the master side of ADR-010.

Phones (and, later, any capture node) register to a session with a join token,
appear on the session page's device panel next to the Polar, and all start
together when the coach hits Start. This is the MVP skeleton: in-memory and
process-local (like `SessionClock` in capture_runner). Persistence, NTP
clock-sync, per-frame shared-clock timestamps, and bell/audio sync are follow-ups
tracked in ADR-010 — the point here is a real, watchable device roster + a single
synchronized start.

Two routers, split by trust boundary:
- `master` (coach, authenticated) — join-info, device roster, start/stop.
- `slave` (phone, join-token) — register, heartbeat, poll capture state.

Survives an API restart (uvicorn --reload restarts on every .py save): the join
token is derived from the capture id (HMAC with the server secret), so a phone's
QR stays valid; a phone the restarted server doesn't know re-joins the roster on
its next heartbeat; and the capture state (command, start time, pause) is kept on
disk in data/capture/, so a recording carries on with the same t = 0.

The same capture routes also serve dataset takes (ADR-013) under `/takes/{id}`
(`take_master` / `take_slave`). A take's clips and pose land in its own folder
(`dataset_store.take_dir`); join and complete are per kind (here for sessions,
`routes/datasets.py` for takes). Takes can't be paused.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from api.deps import db_session, session_repo
from api.routes.auth import SECRET_KEY, require_current_user
from api.routes.pose import PoseFrameIn, _to_landmarks, _to_world
from api.services import cross_check, dataset_store, imu_runner, session_analysis
from contracts import PoseFrame
from store import SessionRepo, SessionStatus

# In-memory coordinator state (process-local, MVP). A device unseen for this long
# drops off the roster; start is scheduled this far ahead so every node begins
# together despite network jitter.
_STALE_MS = 12_000.0
_START_DELAY_MS = 3_000.0
_VIDEO_DIR = Path("data/raw/uploaded")  # per-device clips: {session}.{device}.<ext>
_STATE_DIR = Path("data/capture")  # {capture}.json — command / start time across restarts
_STATE_MAX_AGE_MS = 6 * 3600 * 1000  # a start older than this is a forgotten capture
_MAX_CLIP_BYTES = 2 * 1024 * 1024 * 1024  # a 12-min protocol take from a phone can pass 300 MB


def _now_ms() -> float:
    return time.time() * 1000.0


def _lan_ip() -> str:
    """Best-effort LAN IP of this machine so phones can reach the dashboard/API.

    Opens a UDP socket toward a public address (no packets are sent) and reads
    which local interface the OS would route through.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return str(s.getsockname()[0])
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


@dataclass
class _Device:
    device_id: str
    role: str  # "camera" | "sensor"
    label: str  # "front" / "left" / "45" …
    status: str = "connected"  # connected | ready | recording | error
    last_seen_ms: float = field(default_factory=_now_ms)
    frame: bytes | None = None  # latest preview JPEG for the coach's live grid
    frame_ms: float = 0.0
    punches: int = 0  # live punch count this device has detected (client-side)


@dataclass
class _Coord:
    join_token: str
    devices: dict[str, _Device] = field(default_factory=dict)
    command: str = "idle"  # idle | start | stop
    start_at_ms: float | None = None  # scheduled start on the server wall clock
    paused: bool = False  # coach pressed Pause — nodes hold recording, keep the clip
    last_start_ms: float | None = None  # t = 0 of the latest recording, kept after stop
    stopped_ms: float | None = None  # when the coach pressed Stop (server wall clock)


_lock = threading.Lock()
_coords: dict[UUID, _Coord] = {}


def _join_token(capture_id: UUID) -> str:
    """The capture's join token — derived, not random, so the QR a phone scanned
    stays valid when the API restarts."""
    mac = hmac.new(SECRET_KEY.encode(), f"multicam-join:{capture_id}".encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest())[:16].decode()


def _save_state(capture_id: UUID, c: _Coord) -> None:
    """Persist what a restart must not forget (call with `_lock` held)."""
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        (_STATE_DIR / f"{capture_id}.json").write_text(
            json.dumps(
                {
                    "command": c.command,
                    "start_at_ms": c.start_at_ms,
                    "last_start_ms": c.last_start_ms,
                    "stopped_ms": c.stopped_ms,
                    "paused": c.paused,
                }
            )
        )
    except OSError:
        pass  # best effort — the live recording doesn't depend on it


def _load_state(capture_id: UUID, c: _Coord) -> None:
    try:
        st = json.loads((_STATE_DIR / f"{capture_id}.json").read_text())
    except (OSError, ValueError):
        return
    c.last_start_ms = st.get("last_start_ms")
    c.stopped_ms = st.get("stopped_ms")
    start_at = st.get("start_at_ms")
    if st.get("command") == "start" and start_at and _now_ms() - start_at < _STATE_MAX_AGE_MS:
        c.command, c.start_at_ms, c.paused = "start", start_at, bool(st.get("paused"))
    elif st.get("command") == "stop":
        c.command = "stop"


def _ensure(session_id: UUID) -> _Coord:
    c = _coords.get(session_id)
    if c is None:
        c = _Coord(join_token=_join_token(session_id))
        _load_state(session_id, c)  # after a restart: pick the recording back up
        _coords[session_id] = c
    return c


def _check_token(session_id: UUID, token: str) -> _Coord:
    if not hmac.compare_digest(token.encode(), _join_token(session_id).encode()):
        raise HTTPException(status_code=403, detail="invalid or expired join token")
    return _ensure(session_id)


def started_at_ms(session_id: UUID) -> float | None:
    """When the cameras start/started recording this session (server wall clock, ms),
    or None if no synchronized start is active. Other streams (IMU) align their
    t = 0 to this instant so they share the clips' timeline."""
    with _lock:
        c = _coords.get(session_id)
        if c is None or c.command != "start":
            return None
        return c.start_at_ms


def last_command(capture_id: UUID) -> str | None:
    """The coach's latest command for a capture (idle / start / stop / discard),
    from memory or, after an API restart, from its saved state."""
    with _lock:
        c = _coords.get(capture_id)
        if c is not None:
            return c.command
    try:
        cmd = json.loads((_STATE_DIR / f"{capture_id}.json").read_text()).get("command")
    except (OSError, ValueError, AttributeError):
        return None
    return str(cmd) if cmd else None


def is_active(capture_id: UUID, *, within_ms: float = 15 * 60 * 1000) -> bool:
    """Recording, or a camera seen recently — the empty-session cleanup must not
    delete it (a multi-cam session has no video on disk until Stop uploads it)."""
    now = _now_ms()
    with _lock:
        c = _coords.get(capture_id)
        if c is not None:
            if c.command == "start" or any(
                now - d.last_seen_ms < within_ms for d in c.devices.values()
            ):
                return True
    try:
        st = json.loads((_STATE_DIR / f"{capture_id}.json").read_text())
    except (OSError, ValueError):
        return False
    return st.get("command") == "start" and now - (st.get("start_at_ms") or 0) < _STATE_MAX_AGE_MS


def _saved(capture_id: UUID, key: str) -> float | None:
    try:
        v = json.loads((_STATE_DIR / f"{capture_id}.json").read_text()).get(key)
    except (OSError, ValueError, AttributeError):
        return None
    return float(v) if isinstance(v, int | float) else None


def last_started_at_ms(capture_id: UUID) -> float | None:
    """t = 0 of the latest recording (server wall clock, ms), still known after Stop
    and after an API restart."""
    with _lock:
        c = _coords.get(capture_id)
        if c is not None and c.last_start_ms is not None:
            return c.last_start_ms
    return _saved(capture_id, "last_start_ms")


def stopped_at_ms(capture_id: UUID) -> float | None:
    """When Stop was pressed for the latest recording (server wall clock, ms)."""
    with _lock:
        c = _coords.get(capture_id)
        if c is not None and c.stopped_ms is not None:
            return c.stopped_ms
    return _saved(capture_id, "stopped_ms")


def timeline_now_ms(capture_id: UUID) -> float | None:
    """Now on the capture's timeline: ms since the cameras' synchronized start, or
    None before the start or after Stop. Pauses aren't subtracted — use it for
    dataset takes, which can't be paused (protocol block markers)."""
    with _lock:
        c = _coords.get(capture_id)
        if c is None or c.command != "start" or c.start_at_ms is None:
            return None
        now = _now_ms()
        return now - c.start_at_ms if now >= c.start_at_ms else None


def _take_folder(capture_id: UUID) -> Path | None:
    """The take's folder if this capture is a dataset take, else None (a session).
    Resolved from disk on every call, so it survives an API reload mid-take."""
    return dataset_store.take_dir(capture_id)


def _clip_file(capture_id: UUID, device_id: str, ext: str) -> Path:
    folder = _take_folder(capture_id)
    if folder is not None:
        return dataset_store.clip_path(folder, device_id, ext)
    return _VIDEO_DIR / f"{capture_id}.{device_id}{ext}"


def _clip_meta_file(capture_id: UUID, device_id: str) -> Path:
    folder = _take_folder(capture_id)
    if folder is not None:
        return dataset_store.clip_meta_path(folder, device_id)
    return _VIDEO_DIR / f"{capture_id}.{device_id}.json"


def _live_devices(c: _Coord) -> list[_Device]:
    """Return current devices, pruning any that have gone stale (closed tab, etc.)."""
    now = _now_ms()
    for did in [d for d, dev in c.devices.items() if now - dev.last_seen_ms > _STALE_MS]:
        c.devices.pop(did, None)
    return list(c.devices.values())


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class DeviceOut(BaseModel):
    device_id: str
    role: str
    label: str
    status: str
    punches: int = 0


class JoinInfo(BaseModel):
    join_token: str
    join_path: str
    lan_ip: str  # this machine's LAN IP, so the panel can build a phone-reachable URL


class RegisterBody(BaseModel):
    token: str
    role: str = "camera"
    label: str = "camera"


class RegisterOut(BaseModel):
    device_id: str


class HeartbeatBody(BaseModel):
    token: str
    device_id: str
    status: str = "ready"
    punches: int = 0
    # Sent so a device the server no longer knows (API restarted) can re-join.
    role: str = "camera"
    label: str | None = None


class CaptureState(BaseModel):
    command: str
    start_at_ms: float | None
    server_now_ms: float
    paused: bool = False


class StartOut(BaseModel):
    command: str
    start_at_ms: float
    devices: int


# --------------------------------------------------------------------------
# Master (coach) routes — authenticated
# --------------------------------------------------------------------------

# Routes shared by sessions and takes are defined on prefix-less routers and mounted
# under both `/sessions` and `/takes` at the bottom of this module.
_master = APIRouter()
_session_master = APIRouter()  # session-only: join-info, complete


def join(capture_id: UUID, page_prefix: str) -> JoinInfo:
    """Join token + camera-page path for the QR (`page_prefix` is "/sessions" or
    "/takes"). Callers check the capture exists."""
    with _lock:
        c = _ensure(capture_id)
        return JoinInfo(
            join_token=c.join_token,
            join_path=f"{page_prefix}/{capture_id}/camera?token={c.join_token}",
            lan_ip=_lan_ip(),
        )


@_session_master.post("/{session_id}/multicam/join-info", response_model=JoinInfo)
def join_info(session_id: UUID, sessions: SessionRepo = Depends(session_repo)) -> JoinInfo:
    """Create/return the join token + camera-page path for the QR/link."""
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return join(session_id, "/sessions")


@_master.get("/{session_id}/multicam/devices", response_model=list[DeviceOut])
def list_devices(session_id: UUID) -> list[DeviceOut]:
    """Live roster for the device panel (stale nodes pruned)."""
    with _lock:
        c = _coords.get(session_id)
        if c is None:
            return []
        return [
            DeviceOut(
                device_id=d.device_id,
                role=d.role,
                label=d.label,
                status=d.status,
                punches=d.punches,
            )
            for d in _live_devices(c)
        ]


@_master.post("/{session_id}/multicam/start", response_model=StartOut)
def start_capture(session_id: UUID) -> StartOut:
    """Schedule a synchronized start for every connected node."""
    with _lock:
        c = _coords.get(session_id)
        if c is None or not _live_devices(c):
            raise HTTPException(status_code=409, detail="no devices connected")
        c.command = "start"
        c.start_at_ms = _now_ms() + _START_DELAY_MS
        c.last_start_ms = c.start_at_ms
        c.paused = False
        _save_state(session_id, c)
        imu_runner.set_t0(session_id, c.start_at_ms)  # pre-connected wrists store from t = 0
        out = StartOut(command=c.command, start_at_ms=c.start_at_ms, devices=len(c.devices))
    folder = _take_folder(session_id)
    if folder is not None:
        # A take turns from a draft into a recording here (it joins its dataset's list).
        dataset_store.update_take_json(folder, t0_ms=out.start_at_ms)
    return out


@_master.post("/{session_id}/multicam/pause", response_model=CaptureState)
def pause_capture(session_id: UUID) -> CaptureState:
    """Hold recording on every node — MediaRecorder pauses, the clip is kept, and the
    round timer freezes. Resume continues the same clip; only Stop finalizes."""
    if _take_folder(session_id) is not None:
        # A node applies a pause up to one heartbeat late, which would blur labels.
        raise HTTPException(status_code=409, detail="dataset takes can't be paused")
    with _lock:
        c = _ensure(session_id)
        c.paused = True
        _save_state(session_id, c)
        now = _now_ms()
        imu_runner.pause(session_id, at_ms=now)  # keep the wrist data on the clip's timeline
        return CaptureState(
            command=c.command, start_at_ms=c.start_at_ms, server_now_ms=now, paused=True
        )


@_master.post("/{session_id}/multicam/resume", response_model=CaptureState)
def resume_capture(session_id: UUID) -> CaptureState:
    with _lock:
        c = _ensure(session_id)
        c.paused = False
        _save_state(session_id, c)
        now = _now_ms()
        imu_runner.resume(session_id, at_ms=now)
        return CaptureState(
            command=c.command, start_at_ms=c.start_at_ms, server_now_ms=now, paused=False
        )


@_master.post("/{session_id}/multicam/stop", response_model=CaptureState)
def stop_capture(session_id: UUID) -> CaptureState:
    """End the match: nodes finalize + upload their clips. This is the only command
    that saves — Pause keeps the clip open for Resume."""
    with _lock:
        c = _ensure(session_id)
        c.command = "stop"
        c.start_at_ms = None
        c.paused = False
        c.stopped_ms = _now_ms()
        _save_state(session_id, c)
        return CaptureState(command="stop", start_at_ms=None, server_now_ms=_now_ms())


@_master.post("/{session_id}/multicam/discard", response_model=CaptureState)
def discard_capture(session_id: UUID) -> CaptureState:
    """Delete the recording in progress: nodes stop and drop their clip instead of
    uploading it (the coach's "Delete")."""
    with _lock:
        c = _ensure(session_id)
        c.command = "discard"
        c.start_at_ms = None
        c.paused = False
        _save_state(session_id, c)
        return CaptureState(command="discard", start_at_ms=None, server_now_ms=_now_ms())


def delete_session_clips(session_id: UUID) -> int:
    """Remove a session's per-device clips and their sidecars (its delete)."""
    n = 0
    if _VIDEO_DIR.exists():
        for p in _VIDEO_DIR.glob(f"{session_id}.*"):
            p.unlink(missing_ok=True)
            n += 1
    return n


class CompleteBody(BaseModel):
    duration_ms: float | None = None  # active recording time (pauses excluded)


def _labels(session_id: UUID) -> dict[str, str]:
    """Device labels: the live roster, else what the clip sidecars recorded."""
    with _lock:
        c = _coords.get(session_id)
        live = {d.device_id: d.label for d in c.devices.values()} if c else {}
    return {**session_analysis.clip_labels(_VIDEO_DIR, session_id), **live}


@_session_master.post("/{session_id}/multicam/complete", response_model=dict)
def complete_capture(
    session_id: UUID,
    body: CompleteBody,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> dict[str, object]:
    """Mark the session completed once Stop's clips have landed.

    Not done in `stop` itself: the session page hides the cameras panel as soon as
    the session completes, which would unmount the laptop camera mid-upload. The
    coach UI calls this after it has seen every recording camera's new clip."""
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not list_clips(session_id):
        raise HTTPException(status_code=409, detail="no video was saved for this session")
    if body.duration_ms is not None:
        sessions.attach_artifacts(session_id, duration_ms=body.duration_ms)
    # No camera punch events are stored here: the per-round numbers come from the
    # wrist sensors and the cameras cross-checked (services.cross_check, started
    # by the pose uploads). /multicam/analyze is the old single-camera detector.
    sessions.update_status(session_id, SessionStatus.COMPLETED, end=True)
    return {"status": "completed", "clips": len(list_clips(session_id))}


@_session_master.post("/{session_id}/multicam/analyze", response_model=dict)
def analyze_capture(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    db: DBSession = Depends(db_session),
) -> dict[str, object]:
    """(Re)detect a multi-camera session's punches from its cameras' pose.

    Experimental — not run automatically until the camera detector is calibrated
    for the browser cameras (it over-counts on their pose today)."""
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    if not session_analysis.pose_files(session_id):
        raise HTTPException(status_code=409, detail="no camera pose was uploaded for this session")
    return {"punches": session_analysis.analyze(session_id, db, _labels(session_id))}


# --------------------------------------------------------------------------
# Slave (phone) routes — join-token authenticated
# --------------------------------------------------------------------------

_slave = APIRouter()


@_slave.post("/{session_id}/multicam/register", response_model=RegisterOut)
def register_device(session_id: UUID, body: RegisterBody) -> RegisterOut:
    with _lock:
        c = _check_token(session_id, body.token)
        dev = _Device(device_id=uuid4().hex[:8], role=body.role, label=body.label)
        c.devices[dev.device_id] = dev
        return RegisterOut(device_id=dev.device_id)


@_slave.post("/{session_id}/multicam/heartbeat", response_model=CaptureState)
def heartbeat(session_id: UUID, body: HeartbeatBody) -> CaptureState:
    """Keep a device on the roster + report its status; returns the current command."""
    with _lock:
        c = _check_token(session_id, body.token)
        dev = c.devices.get(body.device_id)
        if dev is None:  # the API restarted since this device registered
            dev = _Device(device_id=body.device_id, role=body.role, label=body.label or body.role)
            c.devices[body.device_id] = dev
        if body.label:
            dev.label = body.label  # renamed on the device (e.g. a phone picking its name)
        dev.status = body.status
        dev.punches = body.punches
        dev.last_seen_ms = _now_ms()
        return CaptureState(
            command=c.command,
            start_at_ms=c.start_at_ms,
            server_now_ms=_now_ms(),
            paused=c.paused,
        )


@_slave.get("/{session_id}/multicam/state", response_model=CaptureState)
def capture_state(session_id: UUID, token: str) -> CaptureState:
    """Poll target: the phone reads command + scheduled start; server_now_ms lets it
    estimate the clock offset for a coarse synchronized start."""
    with _lock:
        c = _check_token(session_id, token)
        return CaptureState(
            command=c.command,
            start_at_ms=c.start_at_ms,
            server_now_ms=_now_ms(),
            paused=c.paused,
        )


@_slave.post("/{session_id}/multicam/upload", response_model=dict)
async def upload_device_clip(
    session_id: UUID,
    token: str = Form(...),
    device_id: str = Form(...),
    file: UploadFile = File(...),
    start_offset_ms: float | None = Form(None),
) -> dict[str, object]:
    """A phone uploads the clip it recorded during the synchronized window, saved
    per-device so the coach ends up with one file per angle. Token-authed (no login).

    `start_offset_ms` is how long after the synchronized start (t = 0) the clip's
    first frame was recorded, measured on the device. It's kept in a sidecar
    (`{session}.{device}.json`) so dataset tools can line the video up with the
    IMU and the labels exactly.
    """
    with _lock:
        _check_token(session_id, token)
    ext = ".mp4" if "mp4" in (file.content_type or "") else ".webm"
    dest = _clip_file(session_id, device_id, ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Written under a temporary name and renamed when complete: a clip only shows up
    # (and counts as saved) once all of it has arrived — a 250 MB clip takes a while.
    part = dest.with_name(dest.name + ".part")
    written = 0
    try:
        with part.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > _MAX_CLIP_BYTES:
                    raise HTTPException(status_code=413, detail="clip exceeds size limit")
                out.write(chunk)
        os.replace(part, dest)
    except BaseException:
        part.unlink(missing_ok=True)  # a dropped or refused upload leaves nothing behind
        raise
    meta = _clip_meta_file(session_id, device_id)
    with _lock:
        c = _coords.get(session_id)
        dev = c.devices.get(device_id) if c else None
        label = dev.label if dev else None
    # Offset for sync; the label lets a later analysis find the laptop camera. An
    # older recording's sidecar is always overwritten.
    meta.write_text(json.dumps({"start_offset_ms": start_offset_ms, "label": label}) + "\n")
    folder = _take_folder(session_id)
    if folder is not None and dataset_store.read_take_json(folder).get("status") == "completed":
        # Landed after Stop & save had finished waiting: list it with the take's clips.
        dataset_store.update_take_json(folder, devices=dataset_store.clips(folder))
    return {"bytes": written, "device_id": device_id, "path": str(dest)}


@_slave.post("/{session_id}/multicam/frame", response_model=dict)
async def post_frame(
    session_id: UUID,
    token: str = Form(...),
    device_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, object]:
    """A phone posts a small preview JPEG (~1 fps) for the coach's live grid."""
    data = await file.read(2 * 1024 * 1024)  # a preview frame; cap to be safe
    with _lock:
        c = _check_token(session_id, token)
        dev = c.devices.get(device_id)
        if dev is not None:
            dev.frame = data
            dev.frame_ms = _now_ms()
            dev.last_seen_ms = _now_ms()
    return {"bytes": len(data)}


@_slave.get("/{session_id}/multicam/frame/{device_id}")
def get_frame(session_id: UUID, device_id: str, token: str) -> Response:
    """Latest preview JPEG for one device — used as an <img> src in the live grid."""
    with _lock:
        c = _check_token(session_id, token)
        dev = c.devices.get(device_id)
        data = dev.frame if dev else None
    if data is None:
        raise HTTPException(status_code=404, detail="no frame yet")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class MulticamPoseBody(BaseModel):
    token: str
    device_id: str
    frames: list[PoseFrameIn]
    duration_ms: float | None = None


@_slave.post("/{session_id}/multicam/pose", response_model=dict)
def upload_device_pose(session_id: UUID, body: MulticamPoseBody) -> dict[str, object]:
    """A phone uploads its pose stream after the round, saved per-device as parquet
    (`{session}.{device}.pose.parquet`) so the camera's detection can be analyzed
    offline with the same tools as the laptop path. Token-authed (no login)."""
    with _lock:
        _check_token(session_id, body.token)
    frames: list[PoseFrame] = []
    for i, f in enumerate(body.frames):
        lms = _to_landmarks(f.landmarks)
        if lms is None:
            continue  # skip malformed frames rather than fail the whole upload
        wls = _to_world(f.world_landmarks) if f.world_landmarks else None
        frames.append(
            PoseFrame(
                session_id=session_id,
                frame_index=i,
                t_ms=f.t_ms,
                landmarks=lms,
                world_landmarks=wls,
            )
        )
    if not frames:
        raise HTTPException(status_code=422, detail="no valid pose frames (need 33 landmarks each)")

    from capture.cv.writer import write_pose_parquet

    folder = _take_folder(session_id)
    if folder is not None:
        path = dataset_store.pose_path(folder, body.device_id)
    else:
        path = session_analysis.POSE_DIR / f"{session_id}.{body.device_id}.pose.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    write_pose_parquet(path, frames)
    # Cross-check this camera against the wrists and the other cameras once
    # every camera's upload has landed (debounced).
    cross_check.schedule(
        "take" if folder is not None else "session", session_id, labels=_labels(session_id)
    )
    return {"frames": len(frames), "path": str(path)}


class ClipInfo(BaseModel):
    device_id: str
    ext: str
    bytes: int
    start_offset_ms: float | None = None  # first frame's time after t = 0 (see upload)


def session_ids_with_video() -> set[str]:
    """Ids of every session with a recorded video on disk — per-device multi-cam clips
    (`{session}.{device}.webm`) or a single uploaded video (`{session}.mp4`). One
    directory scan, so session lists can filter without a lookup per session."""
    if not _VIDEO_DIR.exists():
        return set()
    return {
        p.name.split(".", 1)[0]
        for p in _VIDEO_DIR.iterdir()
        if p.suffix in (".webm", ".mp4") and p.stat().st_size > 0
    }


def _clip_offset(session_id: UUID, device_id: str) -> float | None:
    try:
        meta = json.loads(_clip_meta_file(session_id, device_id).read_text())
        return float(meta["start_offset_ms"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


@_master.get("/{session_id}/multicam/clips", response_model=list[ClipInfo])
def list_clips(session_id: UUID) -> list[ClipInfo]:
    """List a session's recorded per-device clips by scanning disk — so they render
    on the session page for ANY session, not just one live in memory."""
    folder = _take_folder(session_id)
    if folder is not None:
        return [ClipInfo(**c) for c in dataset_store.clips(folder)]
    out: list[ClipInfo] = []
    prefix = f"{session_id}."
    if _VIDEO_DIR.exists():
        for p in sorted(_VIDEO_DIR.glob(f"{session_id}.*")):
            rest = p.name[len(prefix) :]  # "{device_id}.{ext}"
            if "." not in rest:
                continue  # single-cam "{session}.webm" — not a per-device clip
            device_id, ext = rest.rsplit(".", 1)
            if ext in ("webm", "mp4"):
                out.append(
                    ClipInfo(
                        device_id=device_id,
                        ext=ext,
                        bytes=p.stat().st_size,
                        start_offset_ms=_clip_offset(session_id, device_id),
                    )
                )
    return out


@_master.get("/{session_id}/multicam/clip/{device_id}")
def get_clip(session_id: UUID, device_id: str) -> Response:
    """Serve one device's recorded clip for playback (coach-authenticated)."""
    for ext, media in ((".webm", "video/webm"), (".mp4", "video/mp4")):
        p = _clip_file(session_id, device_id, ext)
        if p.exists():
            return Response(content=p.read_bytes(), media_type=media)
    raise HTTPException(status_code=404, detail="no clip for this device")


# --------------------------------------------------------------------------
# Mounts — the shared routes under /sessions (training) and /takes (datasets)
# --------------------------------------------------------------------------

_auth = [Depends(require_current_user)]
master = APIRouter(prefix="/sessions", tags=["capture"], dependencies=_auth)
master.include_router(_master)
master.include_router(_session_master)
slave = APIRouter(prefix="/sessions", tags=["capture"])
slave.include_router(_slave)
take_master = APIRouter(prefix="/takes", tags=["capture"], dependencies=_auth)
take_master.include_router(_master)
take_slave = APIRouter(prefix="/takes", tags=["capture"])
take_slave.include_router(_slave)

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
"""

from __future__ import annotations

import secrets
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel

from api.deps import session_repo
from api.routes.auth import require_current_user
from api.routes.pose import PoseFrameIn, _to_landmarks, _to_world
from contracts import PoseFrame
from store import SessionRepo

# In-memory coordinator state (process-local, MVP). A device unseen for this long
# drops off the roster; start is scheduled this far ahead so every node begins
# together despite network jitter.
_STALE_MS = 12_000.0
_START_DELAY_MS = 3_000.0
_VIDEO_DIR = Path("data/raw/uploaded")  # per-device clips: {session}.{device}.<ext>
_MAX_CLIP_BYTES = 300 * 1024 * 1024


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


_lock = threading.Lock()
_coords: dict[UUID, _Coord] = {}


def _ensure(session_id: UUID) -> _Coord:
    c = _coords.get(session_id)
    if c is None:
        c = _Coord(join_token=secrets.token_urlsafe(12))
        _coords[session_id] = c
    return c


def _check_token(session_id: UUID, token: str) -> _Coord:
    c = _coords.get(session_id)
    if c is None or token != c.join_token:
        raise HTTPException(status_code=403, detail="invalid or expired join token")
    return c


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


class CaptureState(BaseModel):
    command: str
    start_at_ms: float | None
    server_now_ms: float


class StartOut(BaseModel):
    command: str
    start_at_ms: float
    devices: int


# --------------------------------------------------------------------------
# Master (coach) routes — authenticated
# --------------------------------------------------------------------------

master = APIRouter(
    prefix="/sessions", tags=["capture"], dependencies=[Depends(require_current_user)]
)


@master.post("/{session_id}/multicam/join-info", response_model=JoinInfo)
def join_info(session_id: UUID, sessions: SessionRepo = Depends(session_repo)) -> JoinInfo:
    """Create/return the join token + camera-page path for the QR/link."""
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    with _lock:
        c = _ensure(session_id)
        return JoinInfo(
            join_token=c.join_token,
            join_path=f"/sessions/{session_id}/camera?token={c.join_token}",
            lan_ip=_lan_ip(),
        )


@master.get("/{session_id}/multicam/devices", response_model=list[DeviceOut])
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


@master.post("/{session_id}/multicam/start", response_model=StartOut)
def start_capture(session_id: UUID) -> StartOut:
    """Schedule a synchronized start for every connected node."""
    with _lock:
        c = _coords.get(session_id)
        if c is None or not _live_devices(c):
            raise HTTPException(status_code=409, detail="no devices connected")
        c.command = "start"
        c.start_at_ms = _now_ms() + _START_DELAY_MS
        return StartOut(command=c.command, start_at_ms=c.start_at_ms, devices=len(c.devices))


@master.post("/{session_id}/multicam/stop", response_model=CaptureState)
def stop_capture(session_id: UUID) -> CaptureState:
    with _lock:
        c = _ensure(session_id)
        c.command = "stop"
        c.start_at_ms = None
        return CaptureState(command="stop", start_at_ms=None, server_now_ms=_now_ms())


# --------------------------------------------------------------------------
# Slave (phone) routes — join-token authenticated
# --------------------------------------------------------------------------

slave = APIRouter(prefix="/sessions", tags=["capture"])


@slave.post("/{session_id}/multicam/register", response_model=RegisterOut)
def register_device(session_id: UUID, body: RegisterBody) -> RegisterOut:
    with _lock:
        c = _check_token(session_id, body.token)
        dev = _Device(device_id=uuid4().hex[:8], role=body.role, label=body.label)
        c.devices[dev.device_id] = dev
        return RegisterOut(device_id=dev.device_id)


@slave.post("/{session_id}/multicam/heartbeat", response_model=CaptureState)
def heartbeat(session_id: UUID, body: HeartbeatBody) -> CaptureState:
    """Keep a device on the roster + report its status; returns the current command."""
    with _lock:
        c = _check_token(session_id, body.token)
        dev = c.devices.get(body.device_id)
        if dev is not None:
            dev.status = body.status
            dev.punches = body.punches
            dev.last_seen_ms = _now_ms()
        return CaptureState(command=c.command, start_at_ms=c.start_at_ms, server_now_ms=_now_ms())


@slave.get("/{session_id}/multicam/state", response_model=CaptureState)
def capture_state(session_id: UUID, token: str) -> CaptureState:
    """Poll target: the phone reads command + scheduled start; server_now_ms lets it
    estimate the clock offset for a coarse synchronized start."""
    with _lock:
        c = _check_token(session_id, token)
        return CaptureState(command=c.command, start_at_ms=c.start_at_ms, server_now_ms=_now_ms())


@slave.post("/{session_id}/multicam/upload", response_model=dict)
async def upload_device_clip(
    session_id: UUID,
    token: str = Form(...),
    device_id: str = Form(...),
    file: UploadFile = File(...),
) -> dict[str, object]:
    """A phone uploads the clip it recorded during the synchronized window, saved
    per-device so the coach ends up with one file per angle. Token-authed (no login).
    """
    with _lock:
        _check_token(session_id, token)
    ext = ".mp4" if "mp4" in (file.content_type or "") else ".webm"
    _VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    dest = _VIDEO_DIR / f"{session_id}.{device_id}{ext}"
    written = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > _MAX_CLIP_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="clip exceeds size limit")
            out.write(chunk)
    return {"bytes": written, "device_id": device_id, "path": str(dest)}


@slave.post("/{session_id}/multicam/frame", response_model=dict)
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


@slave.get("/{session_id}/multicam/frame/{device_id}")
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


_POSE_DIR = Path("data/processed")


@slave.post("/{session_id}/multicam/pose", response_model=dict)
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

    _POSE_DIR.mkdir(parents=True, exist_ok=True)
    path = _POSE_DIR / f"{session_id}.{body.device_id}.pose.parquet"
    write_pose_parquet(path, frames)
    return {"frames": len(frames), "path": str(path)}


class ClipInfo(BaseModel):
    device_id: str
    ext: str
    bytes: int


@master.get("/{session_id}/multicam/clips", response_model=list[ClipInfo])
def list_clips(session_id: UUID) -> list[ClipInfo]:
    """List a session's recorded per-device clips by scanning disk — so they render
    on the session page for ANY session, not just one live in memory."""
    out: list[ClipInfo] = []
    prefix = f"{session_id}."
    if _VIDEO_DIR.exists():
        for p in sorted(_VIDEO_DIR.glob(f"{session_id}.*")):
            rest = p.name[len(prefix) :]  # "{device_id}.{ext}"
            if "." not in rest:
                continue  # single-cam "{session}.webm" — not a per-device clip
            device_id, ext = rest.rsplit(".", 1)
            if ext in ("webm", "mp4"):
                out.append(ClipInfo(device_id=device_id, ext=ext, bytes=p.stat().st_size))
    return out


@master.get("/{session_id}/multicam/clip/{device_id}")
def get_clip(session_id: UUID, device_id: str) -> Response:
    """Serve one device's recorded clip for playback (coach-authenticated)."""
    for ext, media in ((".webm", "video/webm"), (".mp4", "video/mp4")):
        p = _VIDEO_DIR / f"{session_id}.{device_id}{ext}"
        if p.exists():
            return Response(content=p.read_bytes(), media_type=media)
    raise HTTPException(status_code=404, detail="no clip for this device")

"""Camera studio — phones link once and follow every capture.

Scanning a QR for every session or take is too much friction, so a phone links to
the coach's *studio* once: it opens `/camera?studio=<token>`, keeps that link, and
polls the studio. Whatever capture the coach has open — a training session or a
dataset take — is the studio's *active* capture; every linked phone joins it on
its own (with the capture's join token, `capture_coord._join_token`) and then
follows Start / Stop exactly like a phone that scanned that capture's QR.

The studio token is derived from the coach's user id (HMAC with the server
secret), so it survives API restarts; the active capture is kept on disk in
data/capture/. One studio per coach.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import threading
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import session_repo
from api.routes import capture_coord
from api.routes.auth import SECRET_KEY, require_current_user
from api.services import dataset_store
from store import SessionRepo, User

router = APIRouter(prefix="/v2/studio", tags=["studio"])  # coach, authenticated
public = APIRouter(prefix="/studio", tags=["studio"])  # phones, studio token

_STATE_DIR = Path("data/capture")
_PHONE_STALE_S = 12.0

_lock = threading.Lock()
_active: dict[str, dict[str, str]] = {}  # user id → {"kind", "id"}
_phones: dict[str, dict[str, dict[str, object]]] = {}  # user id → phone id → info


def _sig(user_id: str) -> str:
    mac = hmac.new(SECRET_KEY.encode(), f"studio:{user_id}".encode(), hashlib.sha256)
    return base64.urlsafe_b64encode(mac.digest())[:16].decode()


def studio_token(user_id: str) -> str:
    return f"{UUID(user_id).hex}.{_sig(str(UUID(user_id)))}"


def _user_of(token: str) -> str:
    """The coach a studio token belongs to; 403 if it's not a valid token."""
    try:
        hex_id, sig = token.split(".", 1)
        user_id = str(UUID(hex_id))
    except ValueError as e:
        raise HTTPException(status_code=403, detail="invalid studio link") from e
    if not hmac.compare_digest(sig.encode(), _sig(user_id).encode()):
        raise HTTPException(status_code=403, detail="invalid studio link")
    return user_id


def _state_file(user_id: str) -> Path:
    return _STATE_DIR / f"studio-{user_id}.json"


def _get_active(user_id: str) -> dict[str, str] | None:
    with _lock:
        if user_id in _active:
            return _active[user_id]
    a: dict[str, str] | None
    try:
        raw = json.loads(_state_file(user_id).read_text()).get("active")
        a = {"kind": str(raw["kind"]), "id": str(raw["id"])} if raw else None
    except (OSError, ValueError, KeyError, TypeError):
        a = None
    with _lock:
        if a:
            _active[user_id] = a
        return a


def _live_phones(user_id: str) -> list[dict[str, object]]:
    now = time.time()
    with _lock:
        phones = _phones.get(user_id, {})
        for pid in [p for p, info in phones.items() if now - float(info["seen"]) > _PHONE_STALE_S]:  # type: ignore[arg-type]
            phones.pop(pid, None)
        return [{"phone_id": pid, "label": info["label"]} for pid, info in phones.items()]


# --------------------------------------------------------------------------
# Coach side
# --------------------------------------------------------------------------


class ActiveCapture(BaseModel):
    kind: Literal["session", "take"]
    id: UUID


class StudioOut(BaseModel):
    join_path: str  # /camera?studio=… — the one QR a phone ever needs
    lan_ip: str
    active: ActiveCapture | None
    phones: list[dict[str, object]]


def _studio_out(user_id: str) -> StudioOut:
    a = _get_active(user_id)
    return StudioOut(
        join_path=f"/camera?studio={studio_token(user_id)}",
        lan_ip=capture_coord._lan_ip(),
        active=ActiveCapture(kind=a["kind"], id=UUID(a["id"])) if a else None,  # type: ignore[arg-type]
        phones=_live_phones(user_id),
    )


@router.get("", response_model=StudioOut)
def get_studio(user: User = Depends(require_current_user)) -> StudioOut:
    return _studio_out(str(user.id))


@router.put("/active", response_model=StudioOut)
def set_active(
    body: ActiveCapture,
    user: User = Depends(require_current_user),
    sessions: SessionRepo = Depends(session_repo),
) -> StudioOut:
    """Point the linked phones at this capture (the coach opened it)."""
    exists = (
        sessions.get(body.id) is not None
        if body.kind == "session"
        else dataset_store.take_dir(body.id) is not None
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"{body.kind} not found")
    uid = str(user.id)
    a = {"kind": body.kind, "id": str(body.id)}
    with _lock:
        _active[uid] = a
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_file(uid).write_text(json.dumps({"active": a}))
    except OSError:
        pass  # the in-memory state still works until a restart
    return _studio_out(uid)


# --------------------------------------------------------------------------
# Phone side
# --------------------------------------------------------------------------


class StationActive(BaseModel):
    kind: Literal["session", "take"]
    id: UUID
    join_token: str


class StationState(BaseModel):
    active: StationActive | None


@public.get("/state", response_model=StationState)
def station_state(
    token: str,
    phone_id: str = "",
    label: str = "",
    sessions: SessionRepo = Depends(session_repo),
) -> StationState:
    """A linked phone's poll: which capture to join now (and it's seen as linked)."""
    uid = _user_of(token)
    if phone_id:
        with _lock:
            _phones.setdefault(uid, {})[phone_id[:40]] = {
                "label": label[:40] or "phone",
                "seen": time.time(),
            }
    a = _get_active(uid)
    if not a:
        return StationState(active=None)
    cid = UUID(a["id"])
    exists = (
        sessions.get(cid) is not None
        if a["kind"] == "session"
        else dataset_store.take_dir(cid) is not None
    )
    if not exists:
        return StationState(active=None)  # deleted since — wait for the next capture
    return StationState(
        active=StationActive(
            kind=a["kind"],  # type: ignore[arg-type]
            id=cid,
            join_token=capture_coord._join_token(cid),
        )
    )

"""Camera studio — phones link once and follow every capture.

Scanning a QR for every session or take is too much friction, so a phone links to
the coach's *studio* once: it opens `/camera?studio=<token>`, keeps that link, and
polls the studio. Whatever capture the coach has open — a training session or a
dataset take — is the studio's *active* capture; every linked phone joins it on
its own (with the capture's join token, `capture_coord._join_token`) and then
follows Start / Stop exactly like a phone that scanned that capture's QR.

The studio token is signed for the coach's user id (`signed`, ADR-017): it
survives API restarts, works for 30 days, and "Unlink all phones" voids every
link at once. The active capture is kept on disk in data/capture/. One studio
per coach.

A fight (ADR-063) is a capture too: its two corners are two sessions, so each
linked phone has a corner — red, blue or none — set once on the fight page and
remembered for every fight after. With a fight open, a phone joins its corner's
session (one the coach may record); a phone without a corner waits.
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session as DBSession

from api import access
from api.deps import bout_repo, db_session, session_repo
from api.routes import capture_coord
from api.routes.auth import require_current_user
from api.services import dataset_store, signed
from store import BoutRepo, SessionRepo, User

router = APIRouter(prefix="/v2/studio", tags=["studio"])  # coach, authenticated
public = APIRouter(prefix="/studio", tags=["studio"])  # phones, studio token

_STATE_DIR = Path("data/capture")
_PHONE_STALE_S = 12.0

_lock = threading.Lock()
_active: dict[str, dict[str, str]] = {}  # user id → {"kind", "id"}
_phones: dict[str, dict[str, dict[str, object]]] = {}  # user id → phone id → info


STUDIO_TTL_S = 30 * 24 * 3600  # a phone's studio link works for 30 days (ADR-017)


def _state_file(user_id: str) -> Path:
    return _STATE_DIR / f"studio-{user_id}.json"


def _read_state(user_id: str) -> dict[str, object]:
    try:
        data = json.loads(_state_file(user_id).read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_state(user_id: str, **fields: object) -> None:
    data = {**_read_state(user_id), **fields}
    try:
        _STATE_DIR.mkdir(parents=True, exist_ok=True)
        _state_file(user_id).write_text(json.dumps(data))
    except OSError:
        pass  # in-memory state still works until a restart


def _nonce(user_id: str) -> str:
    """Changes when the coach unlinks every phone — old links stop working."""
    return str(_read_state(user_id).get("nonce") or "0")


def studio_token(user_id: str) -> str:
    """The studio link's token: who it's for, signed, good for STUDIO_TTL_S."""
    uid = str(UUID(user_id))
    return f"{UUID(uid).hex}.{signed.sign('studio', f'{uid}:{_nonce(uid)}', STUDIO_TTL_S)}"


def _user_of(token: str) -> str:
    """The coach a studio token belongs to; 403 if it isn't valid (any more)."""
    try:
        hex_id, rest = token.split(".", 1)
        user_id = str(UUID(hex_id))
    except ValueError as e:
        raise HTTPException(status_code=403, detail="invalid studio link") from e
    if not signed.verify(rest, "studio", f"{user_id}:{_nonce(user_id)}"):
        raise HTTPException(status_code=403, detail="invalid or expired studio link")
    return user_id


def _get_active(user_id: str) -> dict[str, str] | None:
    with _lock:
        if user_id in _active:
            return _active[user_id]
    a: dict[str, str] | None
    try:
        raw = _read_state(user_id).get("active")
        a = {"kind": str(raw["kind"]), "id": str(raw["id"])} if isinstance(raw, dict) else None
    except (KeyError, TypeError):
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
        listed = [(pid, info["label"]) for pid, info in phones.items()]
    corners = _corners(user_id)
    return [{"phone_id": pid, "label": label, "corner": corners.get(pid)} for pid, label in listed]


Corner = Literal["red", "blue"]


def _corners(user_id: str) -> dict[str, str]:
    """Each linked phone's fight corner (ADR-063), remembered on disk."""
    raw = _read_state(user_id).get("corners")
    return (
        {str(k): str(v) for k, v in raw.items() if v in ("red", "blue")}
        if isinstance(raw, dict)
        else {}
    )


# --------------------------------------------------------------------------
# Coach side
# --------------------------------------------------------------------------


class ActiveCapture(BaseModel):
    kind: Literal["session", "take", "bout"]
    id: UUID


class StudioOut(BaseModel):
    join_path: str  # /camera?studio=… — the one QR a phone ever needs
    lan_ip: str
    active: ActiveCapture | None
    phones: list[dict[str, object]]


def _join_token(capture_id: UUID) -> str:
    with capture_coord._lock:
        return capture_coord.current_join_token(capture_id)


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
    bouts: BoutRepo = Depends(bout_repo),
    db: DBSession = Depends(db_session),
) -> StudioOut:
    """Point the linked phones at this capture (the coach opened it) — a session
    you may change, a dataset take as a researcher (ADR-017), or a fight with a
    corner you may record (ADR-063)."""
    viewer = access.Viewer(user, db)
    if body.kind == "session":
        row = sessions.get(body.id)
        if row is not None:
            viewer.require(row.fighter_id, access.Level.TRAINING_WRITE)
    elif body.kind == "bout":
        corners = [s for s in bouts.participants(body.id) if s.removed_at is None]
        if corners and not any(
            viewer.can(s.fighter_id, access.Level.TRAINING_WRITE) for s in corners
        ):
            raise HTTPException(
                status_code=403, detail="Neither corner of this fight is yours to record"
            )
    else:
        access.require_researcher(viewer)
    picked = sessions.get(body.id) if body.kind == "session" else None
    exists = (
        picked is not None and picked.removed_at is None  # a deleted session isn't offered
        if body.kind == "session"
        else bouts.get(body.id) is not None
        if body.kind == "bout"
        else dataset_store.take_dir(body.id) is not None
    )
    if not exists:
        raise HTTPException(status_code=404, detail=f"{body.kind} not found")
    uid = str(user.id)
    a = {"kind": body.kind, "id": str(body.id)}
    with _lock:
        _active[uid] = a
    _write_state(uid, active=a)
    return _studio_out(uid)


class PhoneCorner(BaseModel):
    corner: Corner | None  # None: this phone sits fights out


@router.put("/phones/{phone_id}/corner", response_model=StudioOut)
def set_phone_corner(
    phone_id: str, body: PhoneCorner, user: User = Depends(require_current_user)
) -> StudioOut:
    """Which corner a linked phone films in a fight — remembered for every fight
    after, until it's changed (ADR-063)."""
    uid = str(user.id)
    corners = _corners(uid)
    if body.corner is None:
        corners.pop(phone_id[:40], None)
    else:
        corners[phone_id[:40]] = body.corner
    _write_state(uid, corners=corners)
    return _studio_out(uid)


@router.post("/unlink", response_model=StudioOut)
def unlink_phones(user: User = Depends(require_current_user)) -> StudioOut:
    """Unlink every phone from this coach's studio: their links stop working, and
    the QR shown next is a new one (ADR-017)."""
    uid = str(user.id)
    _write_state(uid, nonce=secrets.token_hex(8))
    with _lock:
        _phones.pop(uid, None)
    return _studio_out(uid)


# --------------------------------------------------------------------------
# Phone side
# --------------------------------------------------------------------------


class StationActive(BaseModel):
    kind: Literal["session", "take"]
    id: UUID
    join_token: str
    # In a fight (ADR-063): the corner this phone films, and the fight.
    corner: Corner | None = None
    bout_id: UUID | None = None


class StationState(BaseModel):
    active: StationActive | None
    note: str | None = None  # why a linked phone is waiting, when it can't join


@public.get("/state", response_model=StationState)
def station_state(
    token: str,
    phone_id: str = "",
    label: str = "",
    sessions: SessionRepo = Depends(session_repo),
    bouts: BoutRepo = Depends(bout_repo),
    db: DBSession = Depends(db_session),
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
    if a["kind"] == "bout":
        return _fight_station(uid, UUID(a["id"]), phone_id[:40], bouts, db)
    cid = UUID(a["id"])
    row = sessions.get(cid) if a["kind"] == "session" else None
    exists = (
        row is not None and row.removed_at is None
        if a["kind"] == "session"
        else dataset_store.take_dir(cid) is not None
    )
    if not exists:
        return StationState(active=None)  # deleted since — wait for the next capture
    return StationState(
        active=StationActive(
            kind=a["kind"],  # type: ignore[arg-type]
            id=cid,
            join_token=_join_token(cid),
        )
    )


def _fight_station(
    uid: str, bout_id: UUID, phone_id: str, bouts: BoutRepo, db: DBSession
) -> StationState:
    """A linked phone with a fight open: its corner's session, if it has a corner,
    the fight has that corner, and the coach may record it (ADR-063)."""
    if bouts.get(bout_id) is None:
        return StationState(active=None)
    corner = _corners(uid).get(phone_id)
    if corner is None:
        return StationState(active=None, note="Pick this phone's corner on the fight page")
    row = next(
        (
            s
            for s in bouts.participants(bout_id)
            if s.removed_at is None and str(getattr(s.corner, "value", s.corner)) == corner
        ),
        None,
    )
    if row is None:
        return StationState(active=None, note=f"This fight has no {corner} corner yet")
    owner = db.get(User, UUID(uid))
    if owner is None or not access.Viewer(owner, db).can(
        row.fighter_id, access.Level.TRAINING_WRITE
    ):
        return StationState(active=None, note=f"The {corner} corner isn't yours to record")
    return StationState(
        active=StationActive(
            kind="session",
            id=row.id,
            join_token=_join_token(row.id),
            corner=corner,  # type: ignore[arg-type]
            bout_id=bout_id,
        )
    )

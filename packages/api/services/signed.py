"""Short-lived signed links (ADR-017, part 2).

Some things a browser loads can't carry a login header: an <img> (the live
camera preview, profile photos), an EventSource (the live heart-rate stream), and
a phone that joined by QR code. They get a link signed instead, bound to what it
opens and when it stops working:

    token = "{expiry, hex}.{HMAC(server secret, purpose|resource|expiry)}"

Checking needs nothing stored — a link still works after the API restarts, until
its time is up — and it can't be stretched or pointed at anything else.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from uuid import UUID

from fastapi import HTTPException

PHOTO_PASS_TTL_S = 24 * 3600


def _mac(purpose: str, resource: str, exp: int) -> str:
    from api.routes.auth import SECRET_KEY  # here, not at import: auth uses this module

    msg = f"{purpose}|{resource}|{exp}".encode()
    digest = hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest)[:22].decode()


def sign(purpose: str, resource: str, ttl_s: float, *, now: float | None = None) -> str:
    """A token for `resource`, good for `purpose` for `ttl_s` seconds."""
    exp = int((time.time() if now is None else now) + ttl_s)
    return f"{exp:x}.{_mac(purpose, resource, exp)}"


def expires(token: str) -> int | None:
    """The token's expiry (epoch seconds), or None if it isn't one of ours."""
    try:
        return int(token.split(".", 1)[0], 16)
    except (ValueError, AttributeError):
        return None


def verify(token: str | None, purpose: str, resource: str, *, now: float | None = None) -> bool:
    """True only for an unexpired token signed for exactly this purpose and resource."""
    if not token or "." not in token:
        return False
    exp = expires(token)
    if exp is None or exp < (time.time() if now is None else now):
        return False
    return hmac.compare_digest(token.split(".", 1)[1], _mac(purpose, resource, exp))


def require_live_link(session_id: UUID, t: str | None = None) -> None:
    """For the live preview and heart-rate streams, which a browser opens without a
    login header: a signed link from `/sessions/{id}/live-links` instead."""
    if not verify(t, "live", str(session_id)):
        raise HTTPException(status_code=401, detail="this live link is missing or has expired")


def photo_pass() -> str:
    """One pass for every profile photo, for a signed-in user — photos load in
    <img> tags, which can't send a login (ADR-017)."""
    return sign("photos", "all", PHOTO_PASS_TTL_S)

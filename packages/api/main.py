"""FastAPI entrypoint.

Run: `uv run uvicorn api.main:app --reload`
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

from api import access
from api.routes import (
    auth,
    bouts,
    cameras,
    capture_coord,
    coaches,
    dataset_export,
    datasets,
    fighters,
    gym_invitations,
    gym_managers,
    gym_staff,
    gyms,
    health,
    hrv,
    imu,
    imu_ble,
    live,
    llm,
    llm_compare,
    physicians,
    pose,
    privacy,
    protocol,
    recordings,
    referees,
    reliance,
    rest_cards,
    round_plans,
    rq1,
    sessions,
    squads,
    studio,
    training,
    video,
)
from api.services import signed
from api.services.photos import photos_root
from common import get_settings, setup_logging
from store import create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(get_settings().log_level)
    create_db_and_tables()
    _bootstrap_admin()
    _warm_up_camera_on_macos()
    yield


def _bootstrap_admin() -> None:
    """Create the first admin account from env vars if none exists.

    Set these on Railway (or any host) to auto-provision on first deploy:
        ALION_ADMIN_EMAIL    — admin login email
        ALION_ADMIN_PASSWORD — admin login password (min 6 chars)
        ALION_ADMIN_NAME     — display name (default: "Admin")

    Safe to leave in place permanently: once an admin exists the check
    is a no-op and no duplicate is ever created.
    """
    import logging

    from sqlmodel import Session, select

    from api.routes.auth import _hash_password
    from store import UserCreate, UserRepo
    from store.database import _engine
    from store.models import User, UserRole

    email = os.environ.get("ALION_ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ALION_ADMIN_PASSWORD", "").strip()
    name = os.environ.get("ALION_ADMIN_NAME", "Admin").strip() or "Admin"

    if not email or not password:
        return  # env vars not set — skip silently

    with Session(_engine) as session:
        existing_admins = session.exec(select(User).where(User.role == UserRole.ADMIN)).first()
        if existing_admins:
            return  # admin already exists — nothing to do

        repo = UserRepo(session)
        existing = repo.get_by_email(email)
        if existing:
            # Account exists but isn't admin — promote it
            repo.update(existing.id, {"role": UserRole.ADMIN, "is_active": True})
            logging.getLogger(__name__).info("Promoted %s to admin.", email)
            return

        repo.create(
            UserCreate(email=email, password=password, name=name, role=UserRole.ADMIN),
            _hash_password(password),
        )
        logging.getLogger(__name__).info("Bootstrap admin created: %s", email)


def _warm_up_camera_on_macos() -> None:
    """Trigger the macOS camera-permission prompt from the main thread.

    OpenCV's AVFoundation backend can only request camera authorization
    from the process's main run loop; opening a webcam from a worker
    thread (where the capture_runner lives) fails silently with
    "not authorized to capture video" until the user has explicitly
    granted permission to the parent python binary.

    This briefly opens camera 0 at startup so macOS asks once, the
    user grants, and every subsequent threaded VideoCapture works.
    """
    import os
    import sys

    if sys.platform != "darwin":
        return
    # NOTE: do *not* set OPENCV_AVFOUNDATION_SKIP_AUTH — that disables
    # the system prompt and silently fails. We want macOS to prompt
    # the user once, here on the main thread; the grant then persists
    # for subsequent worker-thread VideoCapture calls.
    _ = os  # keep the import alive for future tweaks
    try:
        import cv2

        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            cap.read()  # one frame is enough to register access
        cap.release()
    except Exception:
        # CV libs may not be installed in some envs; capture itself
        # surfaces a useful error there. Silent here is fine.
        pass


class PhotoFiles(StaticFiles):
    """Profile photos — faces — only with a photo pass (`?t=`, from
    /auth/photo-pass): an <img> can't send a login (ADR-017)."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            query = parse_qs(scope.get("query_string", b"").decode())
            if not signed.verify((query.get("t") or [None])[0], "photos", "all"):
                await PlainTextResponse("photo link missing or expired", status_code=401)(
                    scope, receive, send
                )
                return
        await super().__call__(scope, receive, send)


app = FastAPI(
    title="RingsideIQ API",
    version="0.1.0",
    description="RingsideIQ (formerly Alion) — multi-modal AI coaching platform for combat sports (DBA dissertation, GGU).",
    lifespan=lifespan,
    # Record-level access control on every route (ADR-017): whose data a route
    # addresses is read from its path, so no route can be left unguarded.
    dependencies=[Depends(access.guard)],
)

# CORS — set ALION_CORS_ORIGINS to a comma-separated list of allowed origins.
# In development this defaults to localhost; in production set it explicitly.
# Example: ALION_CORS_ORIGINS=https://app.yourdomain.com,https://yourdomain.com
_raw_origins = os.environ.get("ALION_CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 1 routes are exposed at both unversioned paths (the dashboard uses
# these) AND under /v1/. The /v1/ surface is the *frozen* contract — Phase 2
# work introduces /v2/ if shapes change. Existing callers never break.
for router in (health.router, cameras.router, fighters.router, sessions.router):
    app.include_router(router)
    app.include_router(router, prefix="/v1")

# MJPEG preview stream — an <img> can't send a login, so it takes a signed link (ADR-017)
app.include_router(sessions.preview_router)
app.include_router(sessions.preview_router, prefix="/v1")

# Phase 2 surface: HRV routes are NEW work, only mounted under /v2.
# Phase 1 (/v1) sees nothing about HRV — preserves the lock from ADR 004.
app.include_router(hrv.router, prefix="/v2")
app.include_router(hrv.stream_router, prefix="/v2")
app.include_router(hrv.ble_router, prefix="/v2")
# Every session's heart-rate and wrist recordings, for the HRV and IMU tabs.
app.include_router(recordings.router, prefix="/v2")
app.include_router(imu.router, prefix="/v2")
app.include_router(imu.router)
# Live wrist IMUs over BLE (WT901 pair) — devices/owner + per-session start/stop/status.
app.include_router(imu_ble.devices_router, prefix="/v2")
app.include_router(imu_ble.router, prefix="/v2")
app.include_router(live.router, prefix="/v2")
app.include_router(protocol.plan_router, prefix="/v2")
app.include_router(protocol.router, prefix="/v2")
app.include_router(dataset_export.router, prefix="/v2")
# Pose-stream upload — persists browser-captured landmarks as parquet so
# browser sessions save pose data (offline eval + RQ2). New endpoint, additive.
app.include_router(pose.router)
# Session video — save + serve the browser-recorded clip for visual review.
app.include_router(video.router)
# Multi-device capture coordinator (ADR-010): device roster + synchronized start.
# master = coach (authenticated); slave = phone (join-token). Additive, isolated.
app.include_router(capture_coord.master)
app.include_router(capture_coord.slave)
app.include_router(capture_coord.take_master)  # dataset takes (ADR-013)
app.include_router(capture_coord.take_slave)
app.include_router(datasets.router)
app.include_router(datasets.capture)
app.include_router(studio.router)  # phones link once, follow every capture
app.include_router(studio.public)
app.include_router(training.router)  # the dataset's camera punch counter
app.include_router(rq1.router)
app.include_router(reliance.router)  # the appropriate-reliance study (ADR-026)
app.include_router(privacy.router)  # what's kept, who sees it, requests (ADR-033)
app.include_router(gym_invitations.router)  # a fighter accepts a gym (ADR-035)
app.include_router(gym_invitations.my_gyms)  # …and leaves one (ADR-050)
app.include_router(gym_invitations.join)  # asks to join with a code (ADR-055)
app.include_router(gym_staff.router)  # a gym's staff (ADR-052)
app.include_router(gym_staff.mine)
app.include_router(squads.router)  # squads within a gym (ADR-053)
app.include_router(llm_compare.router)  # saved language-model comparisons (ADR-058)
app.include_router(rest_cards.router)  # the minute between rounds (ADR-041)
app.include_router(physicians.router)  # a physician's fighters (ADR-046)
app.include_router(round_plans.router)
# Two-fighter bouts (ADR-011) — new endpoints, unversioned.
app.include_router(bouts.router)
app.include_router(llm.router)  # local or remote AI for advice (ADR-021)

# Profile-type expansion (coaches + referees): unversioned only.
# These are NEW endpoints; not part of any frozen contract yet.
app.include_router(auth.router)
app.include_router(coaches.router)
app.include_router(referees.router)
app.include_router(gyms.router)
app.include_router(gym_managers.router)

# Serve uploaded profile photos. Path matches what's stored in the DB:
# data/photos/{kind}/{id}.{ext} → GET /static/photos/{kind}/{id}.{ext}
_photos = photos_root()
_photos.mkdir(parents=True, exist_ok=True)
app.mount("/static/photos", PhotoFiles(directory=str(_photos)), name="photos")

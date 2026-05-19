"""FastAPI entrypoint.

Run: `uv run uvicorn api.main:app --reload`
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import (
    auth,
    cameras,
    coaches,
    fighters,
    gym_managers,
    gyms,
    health,
    hrv,
    imu,
    referees,
    round_plans,
    rq1,
    sessions,
)
from api.services.photos import photos_root
from common import get_settings, setup_logging
from store import create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(get_settings().log_level)
    create_db_and_tables()
    _warm_up_camera_on_macos()
    yield


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


app = FastAPI(
    title="Alion API",
    version="0.1.0",
    description="Alion — multi-modal AI coaching platform for combat sports (DBA dissertation, GGU).",
    lifespan=lifespan,
)

# CORS — dev defaults + any extra origins set via ALION_CORS_ORIGINS env var.
# In production set: ALION_CORS_ORIGINS=https://alion.vercel.app,https://yourdomain.com
import os as _os
_default_origins = ["http://localhost:3000", "http://localhost:3001"]
_extra = _os.environ.get("ALION_CORS_ORIGINS", "")
_allowed_origins = _default_origins + [o.strip() for o in _extra.split(",") if o.strip()]

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

# MJPEG preview stream — no auth (session UUID is the access control, <img> can't send headers)
app.include_router(sessions.preview_router)
app.include_router(sessions.preview_router, prefix="/v1")

# Phase 2 surface: HRV routes are NEW work, only mounted under /v2.
# Phase 1 (/v1) sees nothing about HRV — preserves the lock from ADR 004.
app.include_router(hrv.router, prefix="/v2")
app.include_router(hrv.ble_router, prefix="/v2")
app.include_router(imu.router, prefix="/v2")
app.include_router(imu.router)
app.include_router(rq1.router)
app.include_router(round_plans.router)

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
app.mount("/static/photos", StaticFiles(directory=str(_photos)), name="photos")

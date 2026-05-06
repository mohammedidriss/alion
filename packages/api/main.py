"""FastAPI entrypoint.

Run: `uv run uvicorn api.main:app --reload`
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import cameras, fighters, health, hrv, sessions
from common import get_settings, setup_logging
from store import create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(get_settings().log_level)
    create_db_and_tables()
    yield


app = FastAPI(
    title="Alion API",
    version="0.1.0",
    description="Alion — multi-modal AI coaching platform for combat sports (DBA dissertation, GGU).",
    lifespan=lifespan,
)

# Local-only dev: allow the Next.js dashboard at localhost:3000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
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

# Phase 2 surface: HRV routes are NEW work, only mounted under /v2.
# Phase 1 (/v1) sees nothing about HRV — preserves the lock from ADR 004.
app.include_router(hrv.router, prefix="/v2")

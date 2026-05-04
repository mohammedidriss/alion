"""FastAPI entrypoint.

Run: `uv run uvicorn api.main:app --reload`
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import fighters, health
from common import get_settings, setup_logging
from store import create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    setup_logging(get_settings().log_level)
    create_db_and_tables()
    yield


app = FastAPI(
    title="Combat Intel API",
    version="0.1.0",
    description="Multi-modal AI coaching platform — DBA dissertation, GGU.",
    lifespan=lifespan,
)

# Local-only dev: allow the Next.js dashboard at localhost:3000.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(fighters.router)

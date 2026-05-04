"""Health check — used by CI, dashboard, and pre-flight scripts."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from contracts import SCHEMA_VERSION

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    schema_version: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", schema_version=SCHEMA_VERSION)

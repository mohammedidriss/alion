"""Health checks — used by CI, dashboard, and pre-flight scripts."""

from __future__ import annotations

import importlib.util

from fastapi import APIRouter, Request
from pydantic import BaseModel

from contracts import SCHEMA_VERSION

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    schema_version: str


class CapabilitiesResponse(BaseModel):
    cv_available: bool
    cv_reason: str | None = None
    webcam_likely: bool


def _module_present(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", schema_version=SCHEMA_VERSION)


@router.get("/health/capabilities", response_model=CapabilitiesResponse)
def capabilities() -> CapabilitiesResponse:
    """Reports whether the API process can run CV capture.

    The dashboard hides / disables capture buttons when this returns false.
    """
    have_cv2 = _module_present("cv2")
    have_mp = _module_present("mediapipe")
    cv_available = have_cv2 and have_mp
    reason: str | None = None
    if not cv_available:
        missing = [n for n, ok in [("opencv-python", have_cv2), ("mediapipe", have_mp)] if not ok]
        reason = (
            f"Capture extras not installed: missing {', '.join(missing)}. "
            "This is normal in the default Docker image — run capture on the host."
        )
    # Webcam access from a containerized API on macOS is impossible (no /dev/video
    # passthrough). We can't probe device presence reliably; if cv is missing,
    # webcam definitely won't work either.
    webcam_likely = cv_available
    return CapabilitiesResponse(
        cv_available=cv_available, cv_reason=reason, webcam_likely=webcam_likely
    )


@router.get("/health/routes")
def list_routes(request: Request) -> dict[str, object]:
    """Returns every registered route — use to verify a deployment has the
    expected endpoints without needing to call each one individually.
    E.g. GET /health/routes and check 'POST /sessions/{session_id}/events/bulk' is present.
    """
    routes = [
        {"method": list(r.methods), "path": r.path}
        for r in request.app.routes
        if hasattr(r, "methods")
    ]
    return {"count": len(routes), "routes": sorted(routes, key=lambda r: r["path"])}

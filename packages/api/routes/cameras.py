"""GET /cameras — enumerate available webcam indices the API process can open.

Probes indices 0..MAX-1 by attempting cv2.VideoCapture and immediately releasing.
Returns each successfully-opened index along with its reported resolution. Used
by the dashboard's camera-selector dropdown.

The probe runs only on demand (per request) — fast enough that we don't cache.
If OpenCV isn't installed we return an empty list with a reason field, which
the dashboard surfaces.
"""

from __future__ import annotations

import importlib.util

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["cameras"])

# How many indices to probe. macOS rarely exposes more than 1-2; we cap at 5
# so a clean machine doesn't hang on enumeration.
_MAX_INDEX_TO_PROBE = 5


class Camera(BaseModel):
    index: int
    width: int
    height: int
    fps: float


class CamerasResponse(BaseModel):
    cameras: list[Camera]
    cv_available: bool
    reason: str | None = None


def _probe() -> list[Camera]:
    import cv2

    found: list[Camera] = []
    for i in range(_MAX_INDEX_TO_PROBE):
        cap = cv2.VideoCapture(i)
        if not cap.isOpened():
            cap.release()
            continue
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 30.0)
        cap.release()
        found.append(Camera(index=i, width=w, height=h, fps=fps))
    return found


@router.get("/cameras", response_model=CamerasResponse)
def list_cameras() -> CamerasResponse:
    if importlib.util.find_spec("cv2") is None:
        return CamerasResponse(
            cameras=[],
            cv_available=False,
            reason="OpenCV is not installed in this environment.",
        )
    try:
        cams = _probe()
    except Exception as e:
        return CamerasResponse(cameras=[], cv_available=True, reason=str(e))
    return CamerasResponse(cameras=cams, cv_available=True, reason=None)

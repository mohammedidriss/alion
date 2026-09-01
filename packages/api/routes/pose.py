"""Pose-stream upload — persist browser-captured landmarks as parquet.

Live webcam capture runs MediaPipe in the browser and only bulk-uploads the
detected punch events; the pose frames were being discarded, so sessions saved
no pose data (`frame_count=0`, no parquet). That blocks offline detector
evaluation and the dissertation's RQ2 accuracy study.

This endpoint accepts the per-frame landmarks the browser already has and writes
them to `data/processed/{session_id}.pose.parquet` in the same format the
server-side capture pipeline uses — so `read_pose_parquet`, `scripts/evaluate.py`,
and the second-pass detectors all work on browser-captured sessions too.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.deps import session_repo
from api.routes.auth import require_current_user
from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame, WorldLandmark
from store import SessionRepo, SessionStatus

router = APIRouter(
    prefix="/sessions",
    tags=["pose"],
    dependencies=[Depends(require_current_user)],
)

_DATA_DIR = Path("data/processed")


class PoseFrameIn(BaseModel):
    """One frame: `landmarks` (and optional `world_landmarks`) as 33 × [x, y, z, visibility]."""

    t_ms: float = Field(ge=0.0)
    landmarks: list[list[float]]
    world_landmarks: list[list[float]] | None = None


class PoseBulkBody(BaseModel):
    frames: list[PoseFrameIn]
    duration_ms: float | None = None


def _to_landmarks(rows: list[list[float]]) -> tuple[Landmark, ...] | None:
    if len(rows) != NUM_POSE_LANDMARKS:
        return None
    try:
        return tuple(
            Landmark(x=r[0], y=r[1], z=r[2], visibility=r[3] if len(r) > 3 else 1.0) for r in rows
        )
    except (IndexError, ValueError):
        return None


def _to_world(rows: list[list[float]]) -> tuple[WorldLandmark, ...] | None:
    if len(rows) != NUM_POSE_LANDMARKS:
        return None
    try:
        return tuple(
            WorldLandmark(x=r[0], y=r[1], z=r[2], visibility=r[3] if len(r) > 3 else 1.0)
            for r in rows
        )
    except (IndexError, ValueError):
        return None


@router.post("/{session_id}/pose/bulk", response_model=dict)
def bulk_upload_pose(
    session_id: UUID,
    body: PoseBulkBody,
    repo: SessionRepo = Depends(session_repo),
) -> dict[str, object]:
    """Persist a browser-captured pose stream as parquet and pin it on the session."""
    sess = repo.get(session_id)
    if sess is None:
        raise HTTPException(status_code=404, detail="session not found")

    frames: list[PoseFrame] = []
    for i, f in enumerate(body.frames):
        lms = _to_landmarks(f.landmarks)
        if lms is None:
            continue  # skip malformed frames rather than fail the whole upload
        wls = _to_world(f.world_landmarks) if f.world_landmarks else None
        frames.append(
            PoseFrame(
                session_id=session_id,
                frame_index=i,
                t_ms=f.t_ms,
                landmarks=lms,
                world_landmarks=wls,
            )
        )

    if not frames:
        raise HTTPException(status_code=422, detail="no valid pose frames (need 33 landmarks each)")

    from capture.cv.writer import write_pose_parquet

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = _DATA_DIR / f"{session_id}.pose.parquet"
    write_pose_parquet(path, frames)

    duration = body.duration_ms if body.duration_ms is not None else frames[-1].t_ms
    repo.attach_artifacts(
        session_id,
        pose_parquet_path=str(path),
        frame_count=len(frames),
        duration_ms=duration,
    )
    repo.update_status(session_id, SessionStatus.COMPLETED, end=True)
    return {"frames": len(frames), "path": str(path)}

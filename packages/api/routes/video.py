"""Session video — save and serve the recorded clip for browser capture.

Browser capture can optionally record the webcam clip (MediaRecorder) and upload
it here so a coach can review the punches visually and verify the count. Stored
under data/raw/uploaded/{session_id}.<ext> and pinned on the session's
`video_path`. Distinct from the frozen `uploaded_video` upload in sessions.py,
which is only for the upload-a-file capture source.

Video contains the athlete's face (PII) — kept local-only per ADR 002, served
only to authenticated callers.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from api.deps import session_repo
from api.routes.auth import require_current_user
from store import SessionRepo

router = APIRouter(
    prefix="/sessions",
    tags=["video"],
    dependencies=[Depends(require_current_user)],
)

_VIDEO_DIR = Path("data/raw/uploaded")
_MAX_VIDEO_BYTES = 200 * 1024 * 1024  # 200 MB — generous for a downscaled clip


def _suffix_for(content_type: str | None) -> str:
    ct = (content_type or "").lower()
    if "webm" in ct:
        return ".webm"
    if "mp4" in ct:
        return ".mp4"
    return ".webm"  # MediaRecorder default


@router.post("/{session_id}/video/upload", response_model=dict)
async def upload_session_video(
    session_id: UUID,
    file: UploadFile = File(...),
    sessions: SessionRepo = Depends(session_repo),
) -> dict[str, object]:
    """Save a browser-recorded clip and pin it on the session."""
    row = sessions.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")

    _VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    dest = _VIDEO_DIR / f"{session_id}{_suffix_for(file.content_type)}"
    written = 0
    with dest.open("wb") as out:
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > _MAX_VIDEO_BYTES:
                out.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"video exceeds the {_MAX_VIDEO_BYTES // (1024 * 1024)} MB limit.",
                )
            out.write(chunk)

    sessions.attach_artifacts(session_id, video_path=str(dest))
    return {"video_path": str(dest), "bytes": written}


@router.get("/{session_id}/video")
def get_session_video(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
) -> FileResponse:
    """Stream the saved clip back for playback/review."""
    row = sessions.get(session_id)
    if row is None or not row.video_path:
        raise HTTPException(status_code=404, detail="no video for this session")
    p = Path(row.video_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="video file missing")
    media = "video/webm" if p.suffix == ".webm" else "video/mp4"
    return FileResponse(str(p), media_type=media)

"""Profile photo upload + serve.

Files land in `data/photos/{kind}/{id}.{ext}`. The path stored in the
database is relative (e.g. `data/photos/fighter/abc-123.jpg`); the API
serves these via a static-file route mounted at `/static/photos/...`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, UploadFile

ProfileKind = Literal["fighter", "coach", "referee"]

_ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


def photos_root() -> Path:
    return Path("data/photos")


def delete_photos_for(kind: ProfileKind, profile_id: UUID) -> int:
    """Remove every photo file for this profile (any extension). Returns count
    deleted. Safe to call when no photo exists — returns 0."""
    out_dir = photos_root() / kind
    if not out_dir.exists():
        return 0
    n = 0
    for old in out_dir.glob(f"{profile_id}.*"):
        try:
            old.unlink()
            n += 1
        except OSError:
            pass
    return n


async def save_photo(
    kind: ProfileKind, profile_id: UUID, file: UploadFile
) -> str:
    """Save the upload to disk; return the relative path to persist on the row."""
    name = file.filename or ""
    ext = Path(name).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported image type {ext!r} (allowed: {sorted(_ALLOWED_EXTS)})",
        )
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(body) > _MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"image too large ({len(body)} bytes; max {_MAX_BYTES})",
        )
    out_dir = photos_root() / kind
    out_dir.mkdir(parents=True, exist_ok=True)
    # Wipe any stale ext for this id so old files don't accumulate.
    for old in out_dir.glob(f"{profile_id}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    out_path = out_dir / f"{profile_id}{ext}"
    out_path.write_bytes(body)
    return str(out_path)

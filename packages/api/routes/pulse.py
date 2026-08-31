"""rPPG pulse (PRV) estimation + listing (ADR 008).

Composition-root wiring for the `capture/rppg` adapter. A client uploads an
RGB-trace CSV (per-frame mean colour of a face/skin ROI, extracted between
rounds) plus the capture fps; the adapter estimates pulse and stores PulseSamples.

Pulse-rate variability (PRV), NOT HRV: a distinct cardiac source in its own
`pulse_sample` table, never written to `hr_sample`. Advisory, low-motion
fallback only.
"""

from __future__ import annotations

import csv
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from api.deps import pulse_sample_repo, session_repo
from api.routes.auth import require_current_user
from capture.rppg import RppgWindowSource
from store import PulseSampleRead, PulseSampleRepo, PulseSampleRow, SessionRepo

router = APIRouter(
    prefix="/sessions",
    tags=["pulse"],
    dependencies=[Depends(require_current_user)],
)

_MAX_TRACE_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


def _parse_rgb_trace_csv(text: str) -> list[tuple[float, float, float]]:
    """Parse an RGB-trace CSV (columns r,g,b — one row per frame). Lenient."""
    reader = csv.DictReader(_strip_comments(io.StringIO(text)))
    if reader.fieldnames is None:
        return []
    cols = {c.strip().lower(): c for c in reader.fieldnames}
    if any(ch not in cols for ch in ("r", "g", "b")):
        raise ValueError("RGB-trace CSV must have r, g, b columns")
    trace: list[tuple[float, float, float]] = []
    for row in reader:
        try:
            r = float((row.get(cols["r"]) or "").strip())
            g = float((row.get(cols["g"]) or "").strip())
            b = float((row.get(cols["b"]) or "").strip())
        except ValueError:
            continue
        trace.append((r, g, b))
    return trace


def _strip_comments(lines: io.StringIO) -> list[str]:
    out: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(ln)
    return out


@router.post("/{session_id}/pulse/estimate", response_model=int)
async def estimate_pulse_from_trace(
    session_id: UUID,
    fps: float,
    window_start_ms: float = 0.0,
    min_quality: float = 0.0,
    file: UploadFile = File(...),
    sessions: SessionRepo = Depends(session_repo),
    pulse: PulseSampleRepo = Depends(pulse_sample_repo),
) -> int:
    """Estimate PRV from an uploaded RGB trace; replaces prior pulse samples.

    `fps` is the capture frame rate. `window_start_ms` is the SessionClock T_0
    offset of the trace's first frame (default 0 for a session-relative trace).
    """
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    if fps <= 0:
        raise HTTPException(status_code=422, detail="fps must be positive")
    data = await file.read(_MAX_TRACE_UPLOAD_BYTES + 1)
    if len(data) > _MAX_TRACE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"RGB-trace CSV exceeds the {_MAX_TRACE_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    try:
        trace = _parse_rgb_trace_csv(data.decode("utf-8", errors="ignore"))
    except ValueError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err

    samples = list(
        RppgWindowSource(
            session_id,
            trace,
            fps,
            window_start_ms=window_start_ms,
            min_quality=min_quality,
        )
    )
    rows = [
        PulseSampleRow(
            session_id=s.session_id,
            t_ms=s.t_ms,
            ibi_ms=s.ibi_ms,
            pulse_bpm=s.pulse_bpm,
            quality=s.quality,
        )
        for s in samples
    ]
    return pulse.replace_for_session(session_id, rows)


@router.get("/{session_id}/pulse", response_model=list[PulseSampleRead])
def list_pulse_samples(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    pulse: PulseSampleRepo = Depends(pulse_sample_repo),
) -> list[PulseSampleRead]:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    return [
        PulseSampleRead(
            session_id=r.session_id,
            t_ms=r.t_ms,
            ibi_ms=r.ibi_ms,
            pulse_bpm=r.pulse_bpm,
            quality=r.quality,
            source=r.source,
        )
        for r in pulse.list_for_session(session_id)
    ]

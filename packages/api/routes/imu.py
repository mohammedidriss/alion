"""IMU sample upload + listing.

Until real wrist/glove sensors arrive (Hykso / Corner / phone-IMU bridge),
sessions populate the `imu_sample` table via:

1. `POST /sessions/{id}/imu/upload` — CSV with columns
   `t_ms,ax_g,ay_g,az_g[,gx_dps,gy_dps,gz_dps,hand]`. Replaces any prior
   IMU rows for that session.
2. `POST /sessions/{id}/imu/synth` — generates a synthetic stream from
   the session's existing CV punches. One g-spike per punch event, light
   Gaussian noise around 1g rest. Useful to dry-run the fusion pipeline
   on existing sessions.
3. `GET /sessions/{id}/imu/samples` — ordered by `t_ms`.
"""

from __future__ import annotations

import csv
import io
import math
import random
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlmodel import Session as DBSession

from api.deps import (
    db_session,
    imu_sample_repo,
    punch_event_repo,
    session_repo,
)
from store import (
    HandEnum,
    IMUSampleRead,
    IMUSampleRepo,
    IMUSampleRow,
    PunchEventRepo,
    SessionRepo,
)

router = APIRouter(prefix="/sessions", tags=["imu"])


def _parse_imu_csv(text: str, session_id: UUID) -> list[IMUSampleRow]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="CSV missing header row")
    cols = {c.strip().lower(): c for c in reader.fieldnames}
    required = ["t_ms", "ax_g", "ay_g", "az_g"]
    for r in required:
        if r not in cols:
            raise HTTPException(
                status_code=400,
                detail=f"CSV missing required column '{r}' (got {list(cols.keys())})",
            )
    rows: list[IMUSampleRow] = []
    for row in reader:
        try:
            rows.append(
                IMUSampleRow(
                    session_id=session_id,
                    t_ms=float(row[cols["t_ms"]]),
                    ax_g=float(row[cols["ax_g"]]),
                    ay_g=float(row[cols["ay_g"]]),
                    az_g=float(row[cols["az_g"]]),
                    gx_dps=float(row[cols["gx_dps"]]) if "gx_dps" in cols else 0.0,
                    gy_dps=float(row[cols["gy_dps"]]) if "gy_dps" in cols else 0.0,
                    gz_dps=float(row[cols["gz_dps"]]) if "gz_dps" in cols else 0.0,
                    hand=(
                        HandEnum(row[cols["hand"]])
                        if "hand" in cols and row[cols["hand"]].strip()
                        else None
                    ),
                )
            )
        except (ValueError, KeyError):
            continue
    return rows


@router.post("/{session_id}/imu/upload", response_model=int)
async def upload_imu_csv(
    session_id: UUID,
    file: UploadFile = File(...),
    sessions: SessionRepo = Depends(session_repo),
    imu: IMUSampleRepo = Depends(imu_sample_repo),
) -> int:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    raw = (await file.read()).decode("utf-8", errors="ignore")
    rows = _parse_imu_csv(raw, session_id)
    return imu.replace_for_session(session_id, rows)


@router.post("/{session_id}/imu/synth", response_model=int)
def synthesize_imu(
    session_id: UUID,
    sample_rate_hz: int = 100,
    seed: int = 42,
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    imu: IMUSampleRepo = Depends(imu_sample_repo),
    db: DBSession = Depends(db_session),
) -> int:
    """Synthesize an IMU stream from this session's CV punches.

    Each punch event produces a triangular g-spike around its `t_ms`.
    Useful for dry-running RQ1 (fused-vs-single-modality advice) on
    existing sessions before real wrist sensors are attached.
    """
    row = sessions.get(session_id)
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    if row.duration_ms <= 0:
        raise HTTPException(
            status_code=409,
            detail="session has no duration_ms — finish capture before synthesizing IMU",
        )
    rng = random.Random(seed)
    punches = events.list_for_session(session_id)
    duration_ms = float(row.duration_ms)
    dt_ms = 1000.0 / max(sample_rate_hz, 1)
    samples: list[IMUSampleRow] = []
    t = 0.0
    # Pre-index spikes for fast lookup.
    spikes = sorted([(p.t_ms, p.hand, max(p.velocity_ms, 1.5)) for p in punches])
    spike_window_ms = 60.0  # punch impact spike lasts ~60ms
    while t <= duration_ms:
        # Resting baseline: gravity along z + small noise.
        ax = rng.gauss(0.0, 0.05)
        ay = rng.gauss(0.0, 0.05)
        az = 1.0 + rng.gauss(0.0, 0.05)
        # Add contribution from any nearby punches.
        spike_hand: HandEnum | None = None
        for st_ms, hand, vel in spikes:
            if abs(t - st_ms) <= spike_window_ms:
                # Triangular envelope, peak at the event.
                w = 1.0 - abs(t - st_ms) / spike_window_ms
                # Map velocity (m/s) to peak g — rough scaling.
                peak_g = min(12.0, 2.0 + vel * 1.5)
                ax += w * peak_g * (1.0 if hand == HandEnum.RIGHT else -1.0)
                az += w * peak_g * 0.3
                spike_hand = hand
        samples.append(
            IMUSampleRow(
                session_id=session_id,
                t_ms=t,
                ax_g=round(ax, 3),
                ay_g=round(ay, 3),
                az_g=round(az, 3),
                gx_dps=round(rng.gauss(0.0, 5.0), 2),
                gy_dps=round(rng.gauss(0.0, 5.0), 2),
                gz_dps=round(rng.gauss(0.0, 5.0), 2),
                hand=spike_hand,
            )
        )
        t += dt_ms
    return imu.replace_for_session(session_id, samples)


@router.get("/{session_id}/imu/samples", response_model=list[IMUSampleRead])
def list_imu_samples(
    session_id: UUID,
    sessions: SessionRepo = Depends(session_repo),
    imu: IMUSampleRepo = Depends(imu_sample_repo),
) -> list[IMUSampleRead]:
    if sessions.get(session_id) is None:
        raise HTTPException(status_code=404, detail="session not found")
    rows = imu.list_for_session(session_id)
    # Sub-sample to keep dashboard payloads small (max ~2000 points).
    if len(rows) > 2000:
        step = math.ceil(len(rows) / 2000)
        rows = rows[::step]
    return [
        IMUSampleRead(
            session_id=r.session_id,
            t_ms=r.t_ms,
            ax_g=r.ax_g,
            ay_g=r.ay_g,
            az_g=r.az_g,
            gx_dps=r.gx_dps,
            gy_dps=r.gy_dps,
            gz_dps=r.gz_dps,
            hand=r.hand,
        )
        for r in rows
    ]

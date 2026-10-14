"""What the body sensors stored in each session, summarised — one grouped query
per sensor for any number of sessions.

Used by the HRV and IMU tabs (`routes/recordings.py`, ADR-025) and by the
per-session metrics behind the Observations tab (`services/session_metrics.py`).
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from analyze.hrv_metrics import mean_hr_bpm, rmssd_ms, sdnn_ms
from contracts import HRSample
from store import HRSampleRow, IMUSampleRow

# Beat-to-beat intervals outside 30–200 bpm are dropouts or noise, not heartbeats;
# one of them would swamp RMSSD (a gap of a few seconds reads as thousands of ms).
RR_MIN_MS, RR_MAX_MS = 300.0, 2000.0


@dataclass(frozen=True)
class Heart:
    beats: int  # every stored beat
    duration_s: float
    mean_hr_bpm: float | None  # from the plausible intervals; None when there are none
    max_hr_bpm: float | None
    rmssd_ms: float | None  # None below two plausible beats
    sdnn_ms: float | None


@dataclass(frozen=True)
class Wrist:
    samples: int
    duration_s: float
    hz: float | None
    peak_g: float  # the largest acceleration magnitude stored


def heart(rows: list[tuple[float, float, float]]) -> Heart:
    """One session's beats, in time order: (t_ms, rr_ms, hr_bpm)."""
    beats = [
        HRSample(session_id=UUID(int=0), t_ms=t, rr_ms=rr, hr_bpm=hr)
        for t, rr, hr in rows
        if RR_MIN_MS <= rr <= RR_MAX_MS
    ]
    two = len(beats) >= 2
    return Heart(
        beats=len(rows),
        duration_s=round((rows[-1][0] - rows[0][0]) / 1000.0, 1),
        mean_hr_bpm=round(mean_hr_bpm(beats), 1) if beats else None,
        max_hr_bpm=round(max(b.hr_bpm for b in beats), 1) if beats else None,
        rmssd_ms=round(rmssd_ms(beats), 1) if two else None,
        sdnn_ms=round(sdnn_ms(beats), 1) if two else None,
    )


def heart_by_session(db: DBSession, ids: Sequence[UUID]) -> dict[UUID, Heart]:
    """The heart-rate summary of every listed session the strap stored beats in."""
    beats: dict[UUID, list[tuple[float, float, float]]] = defaultdict(list)
    if not ids:
        return {}
    for sid, t, rr, hr in db.exec(
        select(HRSampleRow.session_id, HRSampleRow.t_ms, HRSampleRow.rr_ms, HRSampleRow.hr_bpm)
        .where(col(HRSampleRow.session_id).in_(ids))
        .order_by(col(HRSampleRow.session_id), col(HRSampleRow.t_ms))
    ).all():
        beats[sid].append((t, rr, hr))
    return {sid: heart(rows) for sid, rows in beats.items()}


def wrists_by_session(db: DBSession, ids: Sequence[UUID]) -> dict[UUID, dict[str, Wrist]]:
    """Per session, per hand ("left" / "right"; "unknown" for unlabelled rows)."""
    out: dict[UUID, dict[str, Wrist]] = defaultdict(dict)
    if not ids:
        return {}
    ax, ay, az = col(IMUSampleRow.ax_g), col(IMUSampleRow.ay_g), col(IMUSampleRow.az_g)
    t_ms = col(IMUSampleRow.t_ms)
    # Grouped in the database — a session holds ~100 rows a second per wrist.
    for sid, hand, n, t0, t1, peak2 in db.execute(
        sa_select(
            col(IMUSampleRow.session_id),
            col(IMUSampleRow.hand),
            func.count(),
            func.min(t_ms),
            func.max(t_ms),
            func.max(ax * ax + ay * ay + az * az),
        )
        .where(col(IMUSampleRow.session_id).in_(ids))
        .group_by(col(IMUSampleRow.session_id), col(IMUSampleRow.hand))
    ).all():
        span_s = (t1 - t0) / 1000.0
        name = str(getattr(hand, "value", hand)) if hand is not None else "unknown"
        out[sid][name] = Wrist(
            samples=n,
            duration_s=round(span_s, 1),
            hz=round((n - 1) / span_s, 1) if n > 1 and span_s > 0 else None,
            peak_g=round(math.sqrt(peak2), 2),
        )
    return dict(out)


def wrist_punches(samples: Sequence[Any]) -> list[tuple[float, str, float, float | None]]:
    """(t_ms, hand, peak g, peak °/s) for each punch the wrist sensors saw
    (`IMUSampleRow`s, any order) — how a session without camera pose counts its
    punches. The rotation is None when the sensor sent none."""
    import numpy as np

    from analyze.imu_punches import detect_punches, peak_rotations

    out: list[tuple[float, str, float, float | None]] = []
    for hand in ("left", "right"):
        rows = sorted(
            (s for s in samples if str(getattr(s.hand, "value", s.hand)) == hand),
            key=lambda s: s.t_ms,
        )
        if len(rows) < 20:
            continue
        t = np.array([r.t_ms for r in rows], dtype=float)
        ev = detect_punches(
            t,
            np.array([r.ax_g for r in rows], dtype=float),
            np.array([r.ay_g for r in rows], dtype=float),
            np.array([r.az_g for r in rows], dtype=float),
        )
        turns = peak_rotations(
            t,
            [r.gx_dps for r in rows],
            [r.gy_dps for r in rows],
            [r.gz_dps for r in rows],
            [e.t_ms for e in ev],
        )
        out += [(float(e.t_ms), hand, float(e.peak_g), r) for e, r in zip(ev, turns, strict=True)]
    return sorted(out)

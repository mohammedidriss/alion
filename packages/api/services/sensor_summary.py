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
from itertools import pairwise
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import Session as DBSession
from sqlmodel import col, select

from analyze.hrv_metrics import artifact_mask, clean_hrv
from store import HRSampleRow, IMUSampleRow


@dataclass(frozen=True)
class Heart:
    beats: int  # every stored beat
    duration_s: float
    mean_hr_bpm: float | None  # from the beats left after artifacts (ADR-037)
    max_hr_bpm: float | None
    rmssd_ms: float | None  # None below two consecutive clean beats
    sdnn_ms: float | None
    artifacts: int  # intervals removed as dropouts, missed or extra beats
    artifact_share: float
    reliable: bool  # at most 5 % removed: the HRV can be read


@dataclass(frozen=True)
class Wrist:
    samples: int
    duration_s: float
    hz: float | None
    peak_g: float  # the largest acceleration magnitude stored


def heart(rows: list[tuple[float, float, float]]) -> Heart:
    """One session's beats, in time order: (t_ms, rr_ms, hr_bpm)."""
    rrs = [rr for _, rr, _ in rows]
    c = clean_hrv(rrs)
    kept_hr = [hr for (_, _, hr), bad in zip(rows, artifact_mask(rrs), strict=True) if not bad]

    def r1(v: float | None) -> float | None:
        return round(v, 1) if v is not None else None

    return Heart(
        beats=len(rows),
        duration_s=round((rows[-1][0] - rows[0][0]) / 1000.0, 1),
        mean_hr_bpm=r1(c.mean_hr_bpm),
        max_hr_bpm=round(max(kept_hr), 1) if kept_hr else None,
        rmssd_ms=r1(c.rmssd_ms),
        sdnn_ms=r1(c.sdnn_ms),
        artifacts=c.artifacts,
        artifact_share=round(c.artifact_share, 3),
        reliable=c.reliable,
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
    return [(p.t_ms, p.hand, p.peak_g, p.peak_dps) for p in wrist_punch_events(samples)]


@dataclass(frozen=True)
class WristPunch:
    t_ms: float
    hand: str
    peak_g: float
    peak_dps: float | None
    clipped: bool  # the sensor's ±16 g range was reached: peak_g is a minimum (ADR-042)


def wrist_punch_events(samples: Sequence[Any]) -> list[WristPunch]:
    """Each punch the wrist sensors saw, with whether its reading clipped — by the
    wrist counter (ADR-060), or the detector's defaults before one is trained."""
    import numpy as np

    from analyze.imu_punches import peak_rotations
    from api.services import wrist_counter

    streams = {}
    for hand in ("left", "right"):
        rows = sorted(
            (s for s in samples if str(getattr(s.hand, "value", s.hand)) == hand),
            key=lambda s: s.t_ms,
        )
        if len(rows) < 20:
            continue
        streams[hand] = (
            np.array([r.t_ms for r in rows], dtype=float),
            np.array(
                [
                    [r.ax_g, r.ay_g, r.az_g, r.gx_dps or 0.0, r.gy_dps or 0.0, r.gz_dps or 0.0]
                    for r in rows
                ],
                dtype=float,
            ),
            rows,
        )
    found = wrist_counter.find({h: (t, imu) for h, (t, imu, _) in streams.items()})
    out: list[WristPunch] = []
    for hand, (t, _imu, rows) in streams.items():
        ev = found.get(hand, [])
        turns = peak_rotations(
            t,
            [r.gx_dps for r in rows],
            [r.gy_dps for r in rows],
            [r.gz_dps for r in rows],
            [e.t_ms for e in ev],
        )
        out += [
            WristPunch(float(e.t_ms), hand, float(e.peak_g), r, e.clipped)
            for e, r in zip(ev, turns, strict=True)
        ]
    return sorted(out, key=lambda p: (p.t_ms, p.hand))


def coverage(times: Sequence[float], start: float, end: float, max_gap_ms: float) -> float | None:
    """The share of [start, end) a stream covered: time between consecutive samples
    counts when the gap is at most `max_gap_ms`; a longer gap is missing, never
    zero (ADR-042). None for an empty window."""
    if end <= start:
        return None
    ts = sorted(t for t in times if start <= t < end)
    if not ts:
        return 0.0
    covered = sum(b - a for a, b in pairwise(ts) if b - a <= max_gap_ms)
    # The edges: up to one gap's worth either side of the first and last sample.
    covered += min(ts[0] - start, max_gap_ms) + min(end - ts[-1], max_gap_ms)
    return round(min(1.0, covered / (end - start)), 3)

"""One session's performance and body-sensor numbers, the same everywhere they're
shown: the Observations tab's trend and the AI observations (ADR-027).

Punches come from where the session settled them, as its per-round breakdown does:

- **cross_check** — a camera session's wrist ↔ camera result (`cross_check`): the
  counted punches, their camera speed and wrist force. Camera sessions store no
  rows in the punch table, so without this they'd read as 0 punches;
- **camera** — the punch table (single-camera and browser sessions);
- **wrist** — the wrist sensors alone, when there's no camera pose;
- **none** — nothing counted.

Heart rate and wrist force come from what the strap and the wrist sensors stored
during the session (`sensor_summary`). The score is unchanged — the
90th-percentile speed × punches per second × minutes — and, like the speed, left
empty when no punch speed was measured (a wrist-only session).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import Session as DBSession
from sqlmodel import col, select

from api.services import cross_check, sensor_summary
from store import IMUSampleRow, PunchEventRow
from store import Session as SessionRow


@dataclass(frozen=True)
class SessionMetrics:
    punch_source: str  # "cross_check" | "camera" | "wrist" | "none"
    punch_count: int
    peak_velocity_ms: float | None  # 90th-percentile punch speed; None when none measured
    ppm: float
    score: float | None
    duration_min: float
    # During the session (the strap and the wrist sensors); None when not recorded.
    mean_hr_bpm: float | None
    max_hr_bpm: float | None
    rmssd_ms: float | None
    peak_wrist_g: float | None  # the largest wrist acceleration stored
    avg_punch_g: float | None  # mean peak force of the counted punches the wrists felt


def p90(values: list[float]) -> float:
    v = sorted(values)
    k = (len(v) - 1) * 0.9
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] * (1 - (k - lo)) + v[hi] * (k - lo)


def _from_cross_check(xc: dict[str, Any]) -> tuple[int, list[float], list[float]]:
    """(count, speeds m/s, wrist peaks g) of the counted punches."""
    counted = [p for p in xc.get("punches", []) if p.get("counted")]
    speeds = [float(p["speed_ms"]) for p in counted if p.get("speed_ms") is not None]
    forces = [float(p["peak_g"]) for p in counted if p.get("peak_g") is not None]
    return len(counted), speeds, forces


def for_sessions(db: DBSession, sessions: Sequence[SessionRow]) -> dict[UUID, SessionMetrics]:
    ids = [s.id for s in sessions]
    events: dict[UUID, list[PunchEventRow]] = defaultdict(list)
    if ids:
        for e in db.exec(select(PunchEventRow).where(col(PunchEventRow.session_id).in_(ids))).all():
            events[e.session_id].append(e)
    hearts = sensor_summary.heart_by_session(db, ids)
    wrists = sensor_summary.wrists_by_session(db, ids)

    # Where each session's punches come from.
    punches: dict[UUID, tuple[str, int, list[float], list[float]]] = {}
    wrist_only: list[UUID] = []
    for s in sessions:
        xc = cross_check.saved_session_result(s.id)
        if xc is not None:
            punches[s.id] = ("cross_check", *_from_cross_check(xc))
        elif events.get(s.id):
            punches[s.id] = ("camera", len(events[s.id]), [e.velocity_ms for e in events[s.id]], [])
        elif s.id in wrists:
            wrist_only.append(s.id)
        else:
            punches[s.id] = ("none", 0, [], [])
    if wrist_only:  # only these need their samples read
        samples: dict[UUID, list[IMUSampleRow]] = defaultdict(list)
        for row in db.exec(
            select(IMUSampleRow).where(col(IMUSampleRow.session_id).in_(wrist_only))
        ).all():
            samples[row.session_id].append(row)
        for sid in wrist_only:
            found = sensor_summary.wrist_punches(samples[sid])
            punches[sid] = ("wrist", len(found), [], [g for _, _, g in found])

    out: dict[UUID, SessionMetrics] = {}
    for s in sessions:
        source, count, speeds, forces = punches[s.id]
        duration_min = (
            (s.duration_ms / 1000.0) / 60.0 if s.duration_ms and s.duration_ms > 0 else 0.0
        )
        ppm = count / duration_min if count and duration_min > 0 else 0.0
        top = p90(speeds) if speeds else None
        heart = hearts.get(s.id)
        hands = wrists.get(s.id, {})
        out[s.id] = SessionMetrics(
            punch_source=source,
            punch_count=count,
            peak_velocity_ms=round(top, 2) if top is not None else None,
            ppm=round(ppm, 1),
            score=round(top * (ppm / 60.0) * duration_min, 2) if top is not None else None,
            duration_min=round(duration_min, 2),
            mean_hr_bpm=heart.mean_hr_bpm if heart else None,
            max_hr_bpm=heart.max_hr_bpm if heart else None,
            rmssd_ms=heart.rmssd_ms if heart else None,
            peak_wrist_g=max(w.peak_g for w in hands.values()) if hands else None,
            avg_punch_g=round(sum(forces) / len(forces), 2) if forces else None,
        )
    return out

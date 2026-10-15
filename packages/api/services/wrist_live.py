"""The wrist sensors' punch count while recording (ADR-059) — the live count to
trust: on the Single round dataset they counted every block exactly, with no
punch on the hand that wasn't throwing, where the cameras' live detector counted
2–4 times too many.

A session's samples are rows in the database, a take's lines in its imu.csv; each
poll reads only what arrived since the last one, then counts each wrist's bursts
with the same detector the cross-check uses (`analyze.imu_punches`).
"""

from __future__ import annotations

import csv
import io
import threading
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID

import numpy as np
import sqlalchemy as sa
from sqlmodel import Session as DBSession
from sqlmodel import col

from analyze.imu_punches import detect_punches
from store import IMUSampleRow

HANDS = ("left", "right")


@dataclass
class _Stream:
    last_id: int = 0  # a session's last row read
    offset: int = 0  # a take's imu.csv bytes read
    names: list[str] = field(default_factory=list)  # a take's imu.csv header
    t: dict[str, list[float]] = field(default_factory=lambda: {h: [] for h in HANDS})
    a: dict[str, list[tuple[float, float, float]]] = field(
        default_factory=lambda: {h: [] for h in HANDS}
    )
    seen: int = -1  # samples when last counted
    counts: dict[str, int] = field(default_factory=dict)


_lock = threading.Lock()
_streams: dict[UUID, _Stream] = {}


def _count(st: _Stream) -> dict[str, int] | None:
    n = sum(len(v) for v in st.t.values())
    if n == 0:
        return None
    if n != st.seen:
        out = {}
        for h in HANDS:
            if len(st.t[h]) < 20:
                out[h] = 0
                continue
            a = np.array(st.a[h], dtype=float)
            out[h] = len(detect_punches(np.array(st.t[h]), a[:, 0], a[:, 1], a[:, 2]))
        st.counts, st.seen = out, n
    return dict(st.counts)


def session_counts(db: DBSession, session_id: UUID) -> dict[str, int] | None:
    """Punches per wrist so far in a session, or None before any sample."""
    with _lock:
        st = _streams.setdefault(session_id, _Stream())
        rows = db.execute(
            sa.select(
                col(IMUSampleRow.id),
                col(IMUSampleRow.t_ms),
                col(IMUSampleRow.ax_g),
                col(IMUSampleRow.ay_g),
                col(IMUSampleRow.az_g),
                col(IMUSampleRow.hand),
            )
            .where(col(IMUSampleRow.session_id) == session_id, col(IMUSampleRow.id) > st.last_id)
            .order_by(col(IMUSampleRow.id))
        ).all()
        for rid, t, ax, ay, az, hand in rows:
            h = str(getattr(hand, "value", hand)).lower()
            if h in HANDS:
                st.t[h].append(float(t))
                st.a[h].append((float(ax), float(ay), float(az)))
            st.last_id = max(st.last_id, int(rid or 0))
        return _count(st)


def take_counts(take_id: UUID, folder: Path | None) -> dict[str, int] | None:
    """Punches per wrist so far in a dataset take (its imu.csv), or None."""
    path = folder / "imu.csv" if folder else None
    if path is None or not path.exists():
        return None
    with _lock:
        st = _streams.setdefault(take_id, _Stream())
        with path.open("rb") as f:
            if st.offset == 0:
                header = f.readline()
                if not header.endswith(b"\n"):
                    return None  # the header isn't written yet
                st.offset, st.names = len(header), header.decode().strip().split(",")
            f.seek(st.offset)
            chunk = f.read()
        complete = chunk[: chunk.rfind(b"\n") + 1]  # a line still being written waits
        st.offset += len(complete)
        for r in csv.DictReader(io.StringIO(complete.decode()), fieldnames=st.names):
            h = r.get("hand", "")
            if h in HANDS:
                try:
                    st.t[h].append(float(r["t_ms"]))
                    st.a[h].append((float(r["ax_g"]), float(r["ay_g"]), float(r["az_g"])))
                except (KeyError, TypeError, ValueError):
                    continue
        return _count(st)


def forget(capture_id: UUID) -> None:
    """Drop a capture's stream (a new recording into it starts over)."""
    with _lock:
        _streams.pop(capture_id, None)

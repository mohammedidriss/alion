"""The wrist sensors' punch count while recording (ADR-059) — the live count: each
wrist counts its own punches, so a still hand that shakes adds little, where the
cameras' live detector counted 2–4 times too many on the Single round dataset.

A session's samples are rows in the database, a take's lines in its imu.csv; each
poll reads only what arrived since the last one, then counts each wrist's punches
with the same counter the cross-check uses (`services.wrist_counter`, ADR-060 —
the detector's defaults missed a third of one fighter's rear hooks and counted an
uppercut's return to guard as a second punch).
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

from api.services import dataset_protocol, wrist_counter
from store import IMUSampleRow

HANDS = ("left", "right")


@dataclass
class _Stream:
    last_id: int = 0  # a session's last row read
    offset: int = 0  # a take's imu.csv bytes read
    names: list[str] = field(default_factory=list)  # a take's imu.csv header
    t: dict[str, list[float]] = field(default_factory=lambda: {h: [] for h in HANDS})
    # ax, ay, az (g), gx, gy, gz (°/s; zeros where none was sent)
    a: dict[str, list[tuple[float, ...]]] = field(default_factory=lambda: {h: [] for h in HANDS})
    seen: int = -1  # samples when last counted
    counts: dict[str, int] = field(default_factory=dict)


_lock = threading.Lock()
_streams: dict[UUID, _Stream] = {}


def _count(st: _Stream) -> dict[str, int] | None:
    n = sum(len(v) for v in st.t.values())
    if n == 0:
        return None
    if n != st.seen:
        found = wrist_counter.find(
            {
                h: (np.array(st.t[h], dtype=float), np.array(st.a[h], dtype=float).reshape(-1, 6))
                for h in HANDS
            }
        )
        st.counts, st.seen = {h: len(found.get(h, [])) for h in HANDS}, n
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
                col(IMUSampleRow.gx_dps),
                col(IMUSampleRow.gy_dps),
                col(IMUSampleRow.gz_dps),
                col(IMUSampleRow.hand),
            )
            .where(col(IMUSampleRow.session_id) == session_id, col(IMUSampleRow.id) > st.last_id)
            .order_by(col(IMUSampleRow.id))
        ).all()
        for rid, t, ax, ay, az, gx, gy, gz, hand in rows:
            h = str(getattr(hand, "value", hand)).lower()
            if h in HANDS:
                st.t[h].append(float(t))
                st.a[h].append(
                    (
                        float(ax),
                        float(ay),
                        float(az),
                        float(gx or 0),
                        float(gy or 0),
                        float(gz or 0),
                    )
                )
            st.last_id = max(st.last_id, int(rid or 0))
        return _count(st)


def take_counts(take_id: UUID, folder: Path | None) -> dict[str, int] | None:
    """Punches per wrist so far in a dataset take (its imu.csv), or None — on the
    right wrists when the take's sensors were marked as worn swapped."""
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
                    row = (
                        float(r["ax_g"]),
                        float(r["ay_g"]),
                        float(r["az_g"]),
                        *(float(r.get(k) or 0.0) for k in ("gx_dps", "gy_dps", "gz_dps")),
                    )
                    st.t[h].append(float(r["t_ms"]))
                    st.a[h].append(row)
                except (KeyError, TypeError, ValueError):
                    continue
        counts = _count(st)
    if counts and folder and dataset_protocol.hands_swapped(dataset_protocol.load(folder)):
        counts = {"left": counts["right"], "right": counts["left"]}
    return counts


def forget(capture_id: UUID) -> None:
    """Drop a capture's stream (a new recording into it starts over)."""
    with _lock:
        _streams.pop(capture_id, None)

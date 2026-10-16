"""The wrist sensors' punch count while recording (ADR-059) — the live count: each
wrist counts its own punches, so a still hand that shakes adds little, where the
cameras' live detector counted 2–4 times too many on the Single round dataset.

A session's samples are rows in the database, a take's lines in its imu.csv; each
poll reads only what arrived since the last one, then counts each wrist's punches
with the same counter the cross-check uses (`services.wrist_counter`, ADR-060 —
the detector's defaults missed a third of one fighter's rear hooks and counted an
uppercut's return to guard as a second punch).

Counting only what's new (review, ADR-064): a punch more than MARGIN_MS before the
newest sample can't change any more — its neighbours on both wrists are in — so it
is counted once and kept; each poll counts again only the tail after it, with
CONTEXT_MS of what came before for the counter's context. Samples older than that
are dropped, so a long session costs no more per poll than a short one. A capture
that starts over (its clock goes back) starts its count over.
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
MARGIN_MS = 4000.0  # a punch this far behind the newest sample is settled
CONTEXT_MS = 4000.0  # what the counter sees before the unsettled tail
RESTART_MS = 1000.0  # a sample this far behind the last one: the capture started over


@dataclass
class _Stream:
    last_id: int = 0  # a session's last row read
    offset: int = 0  # a take's imu.csv bytes read
    names: list[str] = field(default_factory=list)  # a take's imu.csv header
    swapped: bool | None = None  # a take's sensors marked as worn swapped, when read
    t: dict[str, list[float]] = field(default_factory=lambda: {h: [] for h in HANDS})
    # ax, ay, az (g), gx, gy, gz (°/s; zeros where none was sent)
    a: dict[str, list[tuple[float, ...]]] = field(default_factory=lambda: {h: [] for h in HANDS})
    settled_ms: float = float("-inf")  # punches up to here are counted in `settled`
    settled: dict[str, int] = field(default_factory=lambda: dict.fromkeys(HANDS, 0))
    fresh: bool = False  # samples arrived since the last count
    counts: dict[str, int] | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


_lock = threading.Lock()  # the table of streams only; each stream has its own
_streams: dict[UUID, _Stream] = {}


def _stream(capture_id: UUID) -> _Stream:
    with _lock:
        return _streams.setdefault(capture_id, _Stream())


def _add(st: _Stream, hand: str, t: float, row: tuple[float, ...]) -> bool:
    """Add one sample; False if the capture's clock went back (it started over)."""
    ts = st.t[hand]
    if ts and t < ts[-1] - RESTART_MS:
        return False
    ts.append(t)
    st.a[hand].append(row)
    st.fresh = True
    return True


def _reset(st: _Stream) -> None:
    st.t = {h: [] for h in HANDS}
    st.a = {h: [] for h in HANDS}
    st.settled_ms = float("-inf")
    st.settled = dict.fromkeys(HANDS, 0)
    st.counts = None


def _count(st: _Stream) -> dict[str, int] | None:
    if not any(st.t[h] for h in HANDS):
        return None
    if not st.fresh and st.counts is not None:
        return dict(st.counts)
    end = max(st.t[h][-1] for h in HANDS if st.t[h])
    found = wrist_counter.find(
        {
            h: (np.array(st.t[h], dtype=float), np.array(st.a[h], dtype=float).reshape(-1, 6))
            for h in HANDS
        }
    )
    settle_to = end - MARGIN_MS
    counts = {}
    for h in HANDS:
        times = [e.t_ms for e in found.get(h, [])]
        newly = sum(1 for t in times if st.settled_ms < t <= settle_to)
        unsettled = sum(1 for t in times if t > max(st.settled_ms, settle_to))
        st.settled[h] += newly
        counts[h] = st.settled[h] + unsettled
    if settle_to > st.settled_ms:
        st.settled_ms = settle_to
        keep_from = settle_to - CONTEXT_MS
        for h in HANDS:  # what's older than the context is done with
            i = int(np.searchsorted(st.t[h], keep_from))
            if i:
                del st.t[h][:i], st.a[h][:i]
    st.counts, st.fresh = counts, False
    return dict(counts)


def session_counts(db: DBSession, session_id: UUID) -> dict[str, int] | None:
    """Punches per wrist so far in a session, or None before any sample."""
    st = _stream(session_id)
    with st.lock:
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
                row = (
                    float(ax),
                    float(ay),
                    float(az),
                    float(gx or 0),
                    float(gy or 0),
                    float(gz or 0),
                )
                if not _add(st, h, float(t), row):
                    _reset(st)
                    _add(st, h, float(t), row)
            st.last_id = max(st.last_id, int(rid or 0))
        return _count(st)


def take_counts(take_id: UUID, folder: Path | None) -> dict[str, int] | None:
    """Punches per wrist so far in a dataset take (its imu.csv), or None — each
    sample on its real wrist when the take's sensors were marked as worn swapped."""
    path = folder / "imu.csv" if folder else None
    if path is None or folder is None or not path.exists():
        return None
    swapped = dataset_protocol.hands_swapped(dataset_protocol.load(folder))
    st = _stream(take_id)
    with st.lock:
        if st.swapped is not None and st.swapped != swapped:
            _reset(st)  # marked (or unmarked) as swapped: read it again the right way
            st.offset = 0
        st.swapped = swapped
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
            if h not in HANDS:
                continue
            if swapped:
                h = "right" if h == "left" else "left"
            try:
                row = (
                    float(r["ax_g"]),
                    float(r["ay_g"]),
                    float(r["az_g"]),
                    *(float(r.get(k) or 0.0) for k in ("gx_dps", "gy_dps", "gz_dps")),
                )
                t = float(r["t_ms"])
            except (KeyError, TypeError, ValueError):
                continue
            if not _add(st, h, t, row):
                _reset(st)
                _add(st, h, t, row)
        return _count(st)


def forget(capture_id: UUID) -> None:
    """Drop a capture's stream — a new recording into it starts its count over."""
    with _lock:
        _streams.pop(capture_id, None)

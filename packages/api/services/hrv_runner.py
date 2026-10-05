"""HRV runner — orchestrates CSV replay *or* live Polar H10 BLE streaming.

Mirrors `capture_runner` for the CV path: a per-session thread that streams
samples through `analyze.RollingHRMetrics`, persists them to SQLite, and
updates the `Session.status` field.

Lives in `api/services/` (the composition root) because it pulls together
`capture/hrv`, `analyze.hrv_metrics`, and `store`. Feature modules don't
cross-import.

Both `start_replay` (CSV) and `start_ble` (Polar H10) produce the same
`Iterable[HRSample]`; the inner `_run_stream` loop is shared.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager
from pathlib import Path
from uuid import UUID

from sqlmodel import Session as DBSession

from analyze import RollingHRMetrics
from capture.hrv import CsvReplaySource
from common import get_logger
from contracts import HRMetricsWindow, HRSample
from store import HRSampleRow, SessionRepo, SessionStatus

DBFactory = Callable[[], AbstractContextManager[DBSession]]

log = get_logger(__name__)

_active_jobs: dict[UUID, threading.Thread] = {}
_last_error: dict[UUID, str] = {}  # why the latest stream for a capture failed
_recent_bpm: dict[UUID, deque[float]] = {}  # live view, incl. beats before t = 0
_stop_events: dict[UUID, threading.Event] = {}
_latest_metrics: dict[UUID, HRMetricsWindow] = {}
_lock = threading.Lock()


def is_running(session_id: UUID) -> bool:
    with _lock:
        t = _active_jobs.get(session_id)
        return t is not None and t.is_alive()


def recent_bpm(session_id: UUID) -> list[float]:
    """The latest beats' heart rate (oldest first), stored or not — the live reader
    shows the strap working before the cameras start."""
    with _lock:
        return list(_recent_bpm.get(session_id, ()))


def last_error(session_id: UUID) -> str | None:
    """Why the latest heart-rate stream for this capture failed (None if it didn't)."""
    with _lock:
        return _last_error.get(session_id)


def request_stop(session_id: UUID) -> bool:
    with _lock:
        ev = _stop_events.get(session_id)
        if ev is None:
            return False
        ev.set()
        return True


def latest_metrics(session_id: UUID) -> HRMetricsWindow | None:
    with _lock:
        return _latest_metrics.get(session_id)


def _run_stream(
    session_id: UUID,
    source: Iterable[HRSample],
    *,
    source_label: str,
    db_factory: DBFactory | None,
    stop_event: threading.Event,
    window_ms: float = 60_000.0,
    fail_session_on_error: bool = True,
    write_rows: Callable[[list[HRSampleRow]], None] | None = None,
    wall_clock: bool = False,
) -> None:
    """Shared loop for CSV replay and live BLE — consumes any HRSample iterable.

    ``write_rows`` replaces the DB insert — a dataset take streams into its
    ``hr.csv`` instead of ``hrsamplerow`` (ADR-013).

    ``fail_session_on_error`` controls whether an unhandled exception marks the
    *session* as failed.  Set to ``False`` for BLE streams so a device going
    out of range or being unavailable doesn't crash the whole training session.
    """
    log.info(
        "hrv.start",
        extra={"_ctx_session_id": str(session_id), "_ctx_source": source_label},
    )
    rolling = RollingHRMetrics(session_id=session_id, window_ms=window_ms)
    buffered: list[HRSampleRow] = []
    sample_count = 0

    def flush() -> None:
        if not buffered:
            return
        if write_rows is not None:
            write_rows(list(buffered))
        elif db_factory is not None:
            with db_factory() as db:
                for row in buffered:
                    db.add(row)
                db.commit()
        buffered.clear()

    try:
        for sample in source:
            if stop_event.is_set():
                log.info("hrv.stopped", extra={"_ctx_session_id": str(session_id)})
                break
            row = HRSampleRow(
                session_id=sample.session_id,
                # wall_clock: the beat's arrival (epoch ms) — the take's writer puts it
                # on the cameras' timeline; the strap's own clock starts at connect.
                t_ms=time.time() * 1000.0 if wall_clock else sample.t_ms,
                rr_ms=sample.rr_ms,
                hr_bpm=sample.hr_bpm,
            )
            buffered.append(row)
            with _lock:
                _recent_bpm.setdefault(session_id, deque(maxlen=60)).append(sample.hr_bpm)
            window = rolling.feed(sample)
            with _lock:
                _latest_metrics[session_id] = window
            sample_count += 1
            # Flush every 25 samples to keep memory bounded and let
            # downstream API readers see fresh data.
            if len(buffered) >= 25:
                flush()

        flush()  # final flush

        log.info(
            "hrv.done",
            extra={
                "_ctx_session_id": str(session_id),
                "_ctx_samples": sample_count,
                "_ctx_source": source_label,
            },
        )
    except Exception as e:
        log.exception("hrv.failed: %s", e, extra={"_ctx_session_id": str(session_id)})
        with _lock:
            _last_error[session_id] = str(e)[:200] or type(e).__name__
        if fail_session_on_error and db_factory is not None:
            with db_factory() as db:
                SessionRepo(db).update_status(
                    session_id, SessionStatus.FAILED, end=True, failure_reason=str(e)
                )
        else:
            log.warning(
                "hrv.ble_error_ignored: session kept alive — %s",
                e,
                extra={"_ctx_session_id": str(session_id)},
            )
    finally:
        with _lock:
            _active_jobs.pop(session_id, None)
            _stop_events.pop(session_id, None)


def start_replay(
    session_id: UUID,
    csv_path: Path,
    db_factory: DBFactory,
    *,
    realtime: bool = False,
    window_ms: float = 60_000.0,
) -> bool:
    """Spawn the CSV replay in a background thread. Returns False if already running."""
    with _lock:
        if session_id in _active_jobs and _active_jobs[session_id].is_alive():
            return False
        stop_event = threading.Event()
        _stop_events[session_id] = stop_event

    source: Iterable[HRSample] = CsvReplaySource(
        session_id=session_id, path=csv_path, realtime=realtime
    )
    with _lock:
        t = threading.Thread(
            target=_run_stream,
            args=(session_id, source),
            kwargs={
                "source_label": f"csv:{csv_path}",
                "db_factory": db_factory,
                "stop_event": stop_event,
                "window_ms": window_ms,
            },
            daemon=True,
            name=f"hrv-replay-{session_id}",
        )
        _active_jobs[session_id] = t
        t.start()
    return True


def start_ble(
    session_id: UUID,
    address: str,
    db_factory: DBFactory | None,
    *,
    window_ms: float = 60_000.0,
    write_rows: Callable[[list[HRSampleRow]], None] | None = None,
    wall_clock: bool = False,
) -> bool:
    """Spawn Polar H10 BLE streaming in a background thread.

    Returns False if already running. The strap accepts one connection, so any other
    capture still streaming from it is stopped first (newest capture wins).
    """
    with _lock:
        if session_id in _active_jobs and _active_jobs[session_id].is_alive():
            return False
        others = [
            (sid, t)
            for sid, t in _active_jobs.items()
            if sid != session_id and t.is_alive() and t.name.startswith("hrv-ble-")
        ]
        for sid, _ in others:
            ev = _stop_events.get(sid)
            if ev is not None:
                ev.set()
    for sid, t in others:
        log.info("hrv.takeover", extra={"_ctx_session_id": str(session_id), "_ctx_from": str(sid)})
        t.join(timeout=5.0)
    with _lock:
        stop_event = threading.Event()
        _stop_events[session_id] = stop_event
        _last_error.pop(session_id, None)
        _recent_bpm.pop(session_id, None)

    from capture.hrv.polar import PolarH10Source

    source = PolarH10Source(
        session_id=session_id,
        address=address,
        stop_event=stop_event,
    )
    with _lock:
        t = threading.Thread(
            target=_run_stream,
            args=(session_id, source),
            kwargs={
                "source_label": f"ble:{address}",
                "db_factory": db_factory,
                "stop_event": stop_event,
                "window_ms": window_ms,
                "fail_session_on_error": False,
                "write_rows": write_rows,
                "wall_clock": wall_clock,
            },
            daemon=True,
            name=f"hrv-ble-{session_id}",
        )
        _active_jobs[session_id] = t
        t.start()
    return True

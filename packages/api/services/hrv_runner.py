"""HRV runner — orchestrates a CSV replay (for now) in a background thread.

Mirrors `capture_runner` for the CV path: a per-session thread that streams
samples through `analyze.RollingHRMetrics`, persists them to SQLite, and
updates the `Session.status` field.

Lives in `api/services/` (the composition root) because it pulls together
`capture/hrv`, `analyze.hrv_metrics`, and `store`. Feature modules don't
cross-import.

Phase 2 (Polar H10 BLE driver) drops in as another iterable source —
the runner doesn't change.
"""

from __future__ import annotations

import threading
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
_stop_events: dict[UUID, threading.Event] = {}
_latest_metrics: dict[UUID, HRMetricsWindow] = {}
_lock = threading.Lock()


def is_running(session_id: UUID) -> bool:
    with _lock:
        t = _active_jobs.get(session_id)
        return t is not None and t.is_alive()


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


def _run_replay(
    session_id: UUID,
    csv_path: Path,
    *,
    db_factory: DBFactory,
    realtime: bool,
    stop_event: threading.Event,
    window_ms: float = 60_000.0,
) -> None:
    log.info(
        "hrv.start",
        extra={"_ctx_session_id": str(session_id), "_ctx_csv_path": str(csv_path)},
    )
    rolling = RollingHRMetrics(session_id=session_id, window_ms=window_ms)
    buffered: list[HRSampleRow] = []
    sample_count = 0

    def commit_buffer(db: DBSession) -> None:
        for row in buffered:
            db.add(row)
        db.commit()
        buffered.clear()

    try:
        with db_factory() as db:
            SessionRepo(db).update_status(session_id, SessionStatus.CAPTURING)

        source: Iterable[HRSample] = CsvReplaySource(
            session_id=session_id, path=csv_path, realtime=realtime
        )
        for sample in source:
            if stop_event.is_set():
                log.info("hrv.stopped", extra={"_ctx_session_id": str(session_id)})
                break
            row = HRSampleRow(
                session_id=sample.session_id,
                t_ms=sample.t_ms,
                rr_ms=sample.rr_ms,
                hr_bpm=sample.hr_bpm,
            )
            buffered.append(row)
            window = rolling.feed(sample)
            with _lock:
                _latest_metrics[session_id] = window
            sample_count += 1
            # Flush every 25 samples to keep memory bounded and let
            # downstream API readers see fresh data.
            if len(buffered) >= 25:
                with db_factory() as db:
                    commit_buffer(db)

        # Final flush + status update.
        with db_factory() as db:
            commit_buffer(db)
            SessionRepo(db).update_status(session_id, SessionStatus.COMPLETED, end=True)

        log.info(
            "hrv.done",
            extra={
                "_ctx_session_id": str(session_id),
                "_ctx_samples": sample_count,
            },
        )
    except FileNotFoundError as e:
        log.exception("hrv.failed (csv missing): %s", e, extra={"_ctx_session_id": str(session_id)})
        with db_factory() as db:
            SessionRepo(db).update_status(
                session_id,
                SessionStatus.FAILED,
                end=True,
                failure_reason=f"CSV not found: {csv_path}",
            )
    except Exception as e:
        log.exception("hrv.failed: %s", e, extra={"_ctx_session_id": str(session_id)})
        with db_factory() as db:
            SessionRepo(db).update_status(
                session_id, SessionStatus.FAILED, end=True, failure_reason=str(e)
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
    """Spawn the replay in a background thread. Returns False if already running."""
    with _lock:
        if session_id in _active_jobs and _active_jobs[session_id].is_alive():
            return False
        stop_event = threading.Event()
        _stop_events[session_id] = stop_event
        t = threading.Thread(
            target=_run_replay,
            args=(session_id, csv_path),
            kwargs={
                "db_factory": db_factory,
                "realtime": realtime,
                "stop_event": stop_event,
                "window_ms": window_ms,
            },
            daemon=True,
            name=f"hrv-replay-{session_id}",
        )
        _active_jobs[session_id] = t
        t.start()
    return True

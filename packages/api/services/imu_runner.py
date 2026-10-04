"""IMU runner — streams the two WT901 wrist sensors into a session.

Launches `capture.imu.recorder` as a child process (Bluetooth isolated from the
API — see that module), reads its JSON-line samples on a background thread, and
writes `IMUSampleRow`s tagged with the wrist (`hand`).

Timeline: `t_ms` is milliseconds since `t0_ms` — the instant the cameras start
recording (the multi-cam coordinator's start time) — so IMU and video share one
clock. Samples from before t0 (the 3-second countdown) aren't stored; they still
drive the live status, so you can see the sensors are alive before the bell.

Pause mirrors the cameras: MediaRecorder cuts paused time out of the clip, so
samples taken during a pause are dropped and later samples are shifted back by
the paused time — `t_ms` stays on the video's timeline across Pause/Resume.

Lives in `api/services/` (the composition root) alongside `hrv_runner`.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlmodel import Session as DBSession

from common import get_logger
from store import HandEnum, IMUSampleRow

DBFactory = Callable[[], AbstractContextManager[DBSession]]

log = get_logger(__name__)

# Overridable in tests (a fake recorder that needs no Bluetooth).
RECORDER_CMD: list[str] = [sys.executable, "-m", "capture.imu.recorder"]
FLUSH_ROWS = 100
FLUSH_SECONDS = 0.5
# Live reader trace: peak |a| per 50 ms bucket, last 5 s.
TRACE_BUCKET_MS = 50.0
TRACE_POINTS = 100
# Exit codes meaning macOS refused Bluetooth (SIGABRT from CoreBluetooth/TCC).
_TCC_ABORT = {-6, 134}


@dataclass
class UnitState:
    connected: bool = False
    samples: int = 0  # stored samples (t >= t0)
    battery_v: float | None = None
    last_g: float = 0.0
    peak_g: float = 0.0
    error: str | None = None
    recent: deque[float] = field(default_factory=lambda: deque(maxlen=200))  # sensor times, ms
    trace: deque[float] = field(default_factory=lambda: deque(maxlen=TRACE_POINTS))
    _bucket: int = -1

    def observe(self, t_wall_ms: float, g: float) -> None:
        """Feed the live trace: one point per bucket, keeping the bucket's peak so a
        ~30 ms punch spike always shows."""
        b = int(t_wall_ms // TRACE_BUCKET_MS)
        if b == self._bucket and self.trace:
            self.trace[-1] = max(self.trace[-1], g)
        elif b > self._bucket:
            self.trace.append(g)
            self._bucket = b

    def hz(self) -> float:
        if len(self.recent) < 2 or self.recent[-1] <= self.recent[0]:
            return 0.0
        return (len(self.recent) - 1) / ((self.recent[-1] - self.recent[0]) / 1000.0)


@dataclass
class _Job:
    proc: subprocess.Popen[str]
    t0_ms: float
    units: dict[str, UnitState]
    thread: threading.Thread | None = None
    error: str | None = None
    pauses: list[tuple[float, float | None]] = field(default_factory=list)  # wall ms
    stopping: bool = False  # stop() asked for it — a kill on the way out isn't an error

    def timeline_ms(self, t_wall_ms: float) -> float | None:
        """Wall-clock sample time → video-timeline ms, or None if taken while paused."""
        shift = 0.0
        for begin, end in self.pauses:
            if t_wall_ms < begin:
                break
            if end is None or t_wall_ms < end:
                return None
            shift += end - begin
        return t_wall_ms - self.t0_ms - shift


_jobs: dict[UUID, _Job] = {}
_lock = threading.Lock()


def is_running(session_id: UUID) -> bool:
    with _lock:
        job = _jobs.get(session_id)
        return job is not None and job.proc.poll() is None


def any_running() -> bool:
    """True while any session holds the sensors (a unit accepts one connection)."""
    with _lock:
        return any(job.proc.poll() is None for job in _jobs.values())


def check(
    units: dict[str, str], *, seconds: float = 3.0, timeout_s: float = 25.0, rate_hz: float = 100.0
) -> dict[str, Any]:
    """Connect briefly — no session, nothing stored — and report each wrist.

    Streams until every unit has sent `seconds` worth of samples (or `timeout_s`
    passes, e.g. a unit is off), then disconnects so the units advertise again.
    """
    args = [*RECORDER_CMD, "--rate", f"{rate_hz:g}"]
    for hand, addr in units.items():
        args += ["--unit", f"{hand}={addr}"]
    proc = subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1
    )
    states = {h: UnitState() for h in units}
    needed = int(seconds * rate_hz)

    def read() -> None:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            unit = states.get(msg.get("h", ""))
            if unit is None:
                continue
            with _lock:
                if msg.get("k") == "s":
                    ax, ay, az = msg["a"]
                    g = math.sqrt(ax * ax + ay * ay + az * az)
                    unit.connected = True
                    unit.samples += 1
                    unit.recent.append(float(msg["t"]))
                    unit.last_g, unit.peak_g = g, max(unit.peak_g, g)
                elif msg.get("k") == "st":
                    if msg.get("battery_v") is not None:
                        unit.battery_v = float(msg["battery_v"])
                elif msg.get("k") == "err":
                    unit.error = str(msg.get("msg", "error"))

    reader = threading.Thread(target=read, daemon=True, name="imu-check")
    reader.start()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and proc.poll() is None:
        with _lock:
            done = all(u.samples >= needed and u.battery_v is not None for u in states.values())
        if done:
            break
        time.sleep(0.1)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    reader.join(timeout=5)
    code = proc.returncode
    error = None
    if code in _TCC_ABORT:
        error = (
            "macOS denied Bluetooth to the API process. Start the API from your "
            "Terminal (the one where scripts/imu_tool.py works), then try again."
        )
    with _lock:
        return {
            "running": False,
            "error": error,
            "units": {
                hand: {
                    "connected": u.samples > 0,
                    "samples": u.samples,
                    "hz": round(u.hz(), 1),
                    "battery_v": u.battery_v,
                    "last_g": round(u.last_g, 2),
                    "peak_g": round(u.peak_g, 2),
                    "error": None if u.samples else (u.error or "no data — is it switched on?"),
                }
                for hand, u in states.items()
            },
        }


def start(
    session_id: UUID,
    units: dict[str, str],
    t0_ms: float,
    db_factory: DBFactory,
    *,
    rate_hz: float = 100.0,
) -> bool:
    """Start streaming `units` ({hand: address}) into the session. False if already running."""
    with _lock:
        job = _jobs.get(session_id)
        if job is not None and job.proc.poll() is None:
            return False
        args = [*RECORDER_CMD, "--rate", f"{rate_hz:g}"]
        for hand, addr in units.items():
            args += ["--unit", f"{hand}={addr}"]
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        job = _Job(proc=proc, t0_ms=t0_ms, units={h: UnitState() for h in units})
        job.thread = threading.Thread(
            target=_read_stream,
            args=(session_id, job, db_factory),
            daemon=True,
            name=f"imu-{session_id}",
        )
        _jobs[session_id] = job
        job.thread.start()
    log.info("imu.start", extra={"_ctx_session_id": str(session_id)})
    return True


def pause(session_id: UUID, *, at_ms: float | None = None) -> None:
    """The cameras paused: stop storing samples until `resume` (no-op if not running)."""
    at = time.time() * 1000.0 if at_ms is None else at_ms
    with _lock:
        job = _jobs.get(session_id)
        if job is not None and (not job.pauses or job.pauses[-1][1] is not None):
            job.pauses.append((at, None))


def resume(session_id: UUID, *, at_ms: float | None = None) -> None:
    at = time.time() * 1000.0 if at_ms is None else at_ms
    with _lock:
        job = _jobs.get(session_id)
        if job is not None and job.pauses and job.pauses[-1][1] is None:
            begin = job.pauses[-1][0]
            job.pauses[-1] = (begin, max(begin, at))


def stop(session_id: UUID, *, timeout_s: float = 5.0) -> bool:
    """Stop the recorder and wait for the last samples to be written."""
    with _lock:
        job = _jobs.get(session_id)
    if job is None:
        return False
    job.stopping = True
    if job.proc.poll() is None:
        job.proc.terminate()
        try:
            job.proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            job.proc.kill()
    if job.thread is not None:
        job.thread.join(timeout=timeout_s)
    return True


def status(session_id: UUID) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(session_id)
        if job is None:
            return None
        return {
            "running": job.proc.poll() is None,
            "paused": bool(job.pauses) and job.pauses[-1][1] is None,
            "error": job.error,
            "t0_ms": job.t0_ms,
            "units": {
                hand: {
                    "connected": u.connected,
                    "samples": u.samples,
                    "hz": round(u.hz(), 1),
                    "battery_v": u.battery_v,
                    "last_g": round(u.last_g, 2),
                    "peak_g": round(u.peak_g, 2),
                    "error": u.error,
                    "trace": [round(g, 2) for g in u.trace],
                }
                for hand, u in job.units.items()
            },
        }


def timeline_now_ms(session_id: UUID) -> float | None:
    """Now, on the session's IMU/video timeline (ms since the cameras' start, paused
    time removed) — what a stored sample's `t_ms` would read. None when no stream
    is running or it's paused right now. Used to time dataset-protocol blocks."""
    with _lock:
        job = _jobs.get(session_id)
        if job is None or job.proc.poll() is not None:
            return None
        return job.timeline_ms(time.time() * 1000.0)


def _read_stream(session_id: UUID, job: _Job, db_factory: DBFactory) -> None:
    buffered: list[IMUSampleRow] = []
    last_flush = time.monotonic()

    def flush() -> None:
        nonlocal last_flush
        if buffered:
            with db_factory() as db:
                db.add_all(buffered)
                db.commit()
            buffered.clear()
        last_flush = time.monotonic()

    assert job.proc.stdout is not None
    try:
        for line in job.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            unit = job.units.get(msg.get("h", ""))
            if unit is None:
                continue
            kind = msg.get("k")
            if kind == "s":
                ax, ay, az = msg["a"]
                gx, gy, gz = msg["g"]
                g = math.sqrt(ax * ax + ay * ay + az * az)
                with _lock:
                    t_ms = job.timeline_ms(float(msg["t"]))
                    unit.recent.append(float(msg["t"]))
                    unit.observe(float(msg["t"]), g)
                    unit.last_g = g
                    unit.connected = True
                    if t_ms is not None and t_ms >= 0:
                        unit.samples += 1
                        unit.peak_g = max(unit.peak_g, g)
                if t_ms is not None and t_ms >= 0:
                    buffered.append(
                        IMUSampleRow(
                            session_id=session_id,
                            t_ms=t_ms,
                            ax_g=ax,
                            ay_g=ay,
                            az_g=az,
                            gx_dps=gx,
                            gy_dps=gy,
                            gz_dps=gz,
                            hand=HandEnum(msg["h"]),
                        )
                    )
            elif kind == "st":
                with _lock:
                    unit.connected = bool(msg.get("connected"))
                    if msg.get("battery_v") is not None:
                        unit.battery_v = float(msg["battery_v"])
                    if unit.connected:
                        unit.error = None
            elif kind == "err":
                with _lock:
                    unit.error = str(msg.get("msg", "error"))
            if len(buffered) >= FLUSH_ROWS or time.monotonic() - last_flush >= FLUSH_SECONDS:
                flush()
        flush()
    except Exception:
        log.exception("imu.reader_failed", extra={"_ctx_session_id": str(session_id)})
    code = job.proc.wait()
    with _lock:
        for unit in job.units.values():
            unit.connected = False
        if code in _TCC_ABORT:
            job.error = (
                "macOS denied Bluetooth to the API process. Start the API from your "
                "Terminal (the one where scripts/imu_tool.py works), then try again."
            )
        elif code not in (0, -15) and job.error is None and not job.stopping:
            job.error = f"IMU recorder exited unexpectedly (code {code})."
    log.info("imu.done", extra={"_ctx_session_id": str(session_id), "_ctx_exit": code})

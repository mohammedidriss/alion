"""Stream health (ADR-042): each live stream as OK, degraded, lost or recovering.

From the RingsideIQ review board's blueprint. Every stream — each camera, each
wrist, the chest strap — is judged on what it delivered lately, and a stream
that was lost comes back through "recovering" before it is trusted again. The
advice never waits for a stream; a card says which streams it used, and a gap is
stored as missing, never as zero.

| stream | OK | degraded | lost | recovering → OK |
|---|---|---|---|---|
| wrist | ≥ 90 % of 100 Hz, sample < 0.5 s ago | 50–90 %, or a gap up to 2 s | no sample for 2 s, or disconnected | 3 s at OK |
| strap | a beat < 3 s ago, artifacts ≤ 5 % of the last 30 | artifacts > 5 %, or 3–5 s since a beat | no beat for 5 s | 10 s at OK |
| camera | heard from < 2 s ago, recording or ready | 2–6 s, or its app in the background | not heard from for 6 s | 2 s at OK |
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from analyze.hrv_metrics import artifact_mask

State = Literal["ok", "degraded", "lost", "recovering", "off"]
NOMINAL_HZ = 100.0
RECOVER_S = {"wrist": 3.0, "heart": 10.0, "camera": 2.0}


@dataclass
class StreamState:
    key: str  # "camera:<device>", "wrist:left", "heart"
    kind: Literal["camera", "wrist", "heart"]
    label: str
    state: State
    reason: str | None = None


_lock = threading.Lock()
# (capture, stream) → (last raw state, when it last turned ok after a loss, was lost)
_memory: dict[tuple[UUID, str], dict[str, Any]] = {}


def _settle(capture_id: UUID, key: str, kind: str, raw: State, now_s: float) -> State:
    """A stream back from lost is "recovering" until it has been OK long enough."""
    with _lock:
        m = _memory.setdefault((capture_id, key), {"lost": False, "ok_since": None})
        if raw == "lost":
            m["lost"], m["ok_since"] = True, None
            return raw
        if raw == "ok" and m["lost"]:
            if m["ok_since"] is None:
                m["ok_since"] = now_s
            if now_s - m["ok_since"] < RECOVER_S[kind]:
                return "recovering"
            m["lost"] = False
        elif raw != "ok":
            m["ok_since"] = None
        return raw


def wrist_state(unit: dict[str, Any]) -> tuple[State, str | None]:
    ago = unit.get("last_ms_ago")
    hz = float(unit.get("hz") or 0.0)
    if not unit.get("connected") or ago is None or ago >= 2000:
        return "lost", "not connected" if not unit.get("connected") else "no data for 2 s"
    if hz < 0.5 * NOMINAL_HZ:
        return "degraded", f"{round(hz)} readings a second"
    if hz < 0.9 * NOMINAL_HZ or ago >= 500:
        return (
            "degraded",
            f"{round(hz)} readings a second" if hz < 0.9 * NOMINAL_HZ else "a gap in the data",
        )
    return "ok", None


def heart_state(
    running: bool, last_beat_ago_ms: float | None, rrs: list[float]
) -> tuple[State, str | None]:
    if not running or last_beat_ago_ms is None or last_beat_ago_ms >= 5000:
        return "lost", "not connected" if not running else "no beat for 5 s"
    recent = rrs[-30:]
    share = sum(artifact_mask(recent)) / len(recent) if len(recent) >= 10 else 0.0
    if share > 0.05:
        return "degraded", "noisy contact — wet the strap"
    if last_beat_ago_ms >= 3000:
        return "degraded", "beats slowing to arrive"
    return "ok", None


def camera_state(device: dict[str, Any]) -> tuple[State, str | None]:
    age = float(device.get("age_ms") or 0.0)
    status = str(device.get("status") or "")
    if age >= 6000:
        return "lost", "not heard from for 6 s"
    if status == "hidden":
        return "degraded", "the camera app is in the background"
    if age >= 2000 or status in ("loading", "error"):
        return "degraded", "slow to answer" if age >= 2000 else status
    return "ok", None


def snapshot(capture_id: UUID) -> list[StreamState]:
    """Every stream this capture uses, judged now."""
    from api.routes import capture_coord
    from api.services import hrv_runner, imu_runner

    now_s = time.monotonic()
    out: list[StreamState] = []
    for d in sorted(
        capture_coord.device_health(capture_id), key=lambda d: d["label"] or d["device_id"]
    ):
        raw, why = camera_state(d)
        key = f"camera:{d['device_id']}"
        out.append(
            StreamState(
                key,
                "camera",
                d["label"] or "camera",
                _settle(capture_id, key, "camera", raw, now_s),
                why,
            )
        )
    imu = imu_runner.status(capture_id)
    if imu is not None:
        for hand, unit in sorted(imu["units"].items()):
            raw, why = wrist_state(unit)
            key = f"wrist:{hand}"
            out.append(
                StreamState(
                    key,
                    "wrist",
                    f"{hand} wrist",
                    _settle(capture_id, key, "wrist", raw, now_s),
                    why,
                )
            )
    running = hrv_runner.is_running(capture_id)
    last = hrv_runner.last_beat_ms(capture_id)
    if running or last is not None:
        ago = time.time() * 1000.0 - last if last is not None else None
        raw, why = heart_state(running, ago, hrv_runner.recent_rr(capture_id))
        out.append(
            StreamState(
                "heart",
                "heart",
                "heart strap",
                _settle(capture_id, "heart", "heart", raw, now_s),
                why,
            )
        )
    return out

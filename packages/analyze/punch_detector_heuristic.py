"""Heuristic punch-event detector.

Phase 1 placeholder — replaced by the trained LSTM classifier in Phase 3.
This is intentionally crude: it flags an event when a wrist's forward speed
crosses a threshold then decelerates. It will misfire on fast pull-backs and
won't tell punch types apart. Treat it as a "the pipeline is alive" indicator,
not a measurement.

Detector inputs are pose-normalized coordinates [0,1]. Velocity is reported in
those normalized units per second, then scaled by an assumed body-width factor
to give a rough m/s estimate. The real velocity comes from the IMU stream
(Phase 1 Week 3); this is a stand-in until fusion lands.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from contracts import PoseFrame, PunchEvent

# MediaPipe Pose landmark indices.
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12

# Tuned for Phase 1 sanity-checking on a webcam at ~1m distance.
DEFAULT_THRESHOLD_NORM_PER_S = 1.5  # normalized units / s on the image plane
DEFAULT_REFRACTORY_MS = 300.0  # min spacing between two events on the same hand
DEFAULT_BODY_WIDTH_M = 0.45  # rough shoulder width — for m/s estimate
DEFAULT_MIN_VISIBILITY = 0.5


@dataclass
class _HandState:
    last_x: float | None = None
    last_y: float | None = None
    last_t: float | None = None
    last_speed: float = 0.0
    last_event_t: float | None = None


class HeuristicPunchDetector:
    def __init__(
        self,
        *,
        threshold_norm_per_s: float = DEFAULT_THRESHOLD_NORM_PER_S,
        refractory_ms: float = DEFAULT_REFRACTORY_MS,
        body_width_m: float = DEFAULT_BODY_WIDTH_M,
        min_visibility: float = DEFAULT_MIN_VISIBILITY,
    ) -> None:
        self.threshold = threshold_norm_per_s
        self.refractory_ms = refractory_ms
        self.body_width_m = body_width_m
        self.min_visibility = min_visibility
        self._left = _HandState()
        self._right = _HandState()

    def feed(self, frame: PoseFrame) -> list[PunchEvent]:
        events: list[PunchEvent] = []
        ev_l = self._step(frame, "left", LM_LEFT_WRIST, self._left)
        if ev_l is not None:
            events.append(ev_l)
        ev_r = self._step(frame, "right", LM_RIGHT_WRIST, self._right)
        if ev_r is not None:
            events.append(ev_r)
        return events

    def _step(self, frame: PoseFrame, hand: str, lm_idx: int, st: _HandState) -> PunchEvent | None:
        lm = frame.landmarks[lm_idx]
        if lm.visibility < self.min_visibility:
            st.last_x = st.last_y = st.last_t = None
            st.last_speed = 0.0
            return None
        ev: PunchEvent | None = None
        if st.last_t is not None and st.last_x is not None and st.last_y is not None:
            dt_s = max(1e-3, (frame.t_ms - st.last_t) / 1000.0)
            dx = lm.x - st.last_x
            dy = lm.y - st.last_y
            speed = (dx * dx + dy * dy) ** 0.5 / dt_s  # normalized units/s
            crossed_threshold = speed >= self.threshold
            decelerating = speed < st.last_speed
            spaced = st.last_event_t is None or (frame.t_ms - st.last_event_t) >= self.refractory_ms
            if crossed_threshold and decelerating and spaced:
                # Convert normalized speed → m/s using assumed body width.
                v_ms = st.last_speed * self.body_width_m
                # Crude confidence: how far past threshold we got, capped.
                conf = max(0.1, min(1.0, (st.last_speed - self.threshold) / self.threshold))
                ev = PunchEvent(
                    session_id=frame.session_id,
                    t_ms=frame.t_ms,
                    hand=hand,  # type: ignore[arg-type]
                    velocity_ms=round(v_ms, 2),
                    detected_by="heuristic",
                    confidence=round(conf, 2),
                )
                st.last_event_t = frame.t_ms
            st.last_speed = speed
        st.last_x, st.last_y, st.last_t = lm.x, lm.y, frame.t_ms
        return ev


def detect_punches(frames: Iterable[PoseFrame]) -> list[PunchEvent]:
    """One-shot helper for offline / batch detection."""
    det = HeuristicPunchDetector()
    out: list[PunchEvent] = []
    for f in frames:
        out.extend(det.feed(f))
    return out

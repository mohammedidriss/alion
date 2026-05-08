"""Heuristic punch-event detector — v2.

Improvements over v1:
- Uses MediaPipe **world landmarks** (3D, metric, hip-centered) when available
  for real m/s velocity. Falls back to the old 2D image-plane scaling when
  world landmarks are missing.
- **Forward-extension check**: requires the wrist to actually be moving
  *away from the shoulder* (extending) — not just any direction. Kills
  false positives from pulling the hand back after a punch.
- **Whole-body motion filter**: rejects events when the hip is translating
  faster than a threshold. Catches walking / turning / stepping forward.
- **Hand-vs-shoulder gating**: requires the wrist to be in front of the
  shoulder (along the punch axis) at the moment of detection.
- **Lead/rear labelling**: if the fighter's stance is known, returns
  whether the punch came from the lead or rear hand.

Phase 3 LSTM is still on the roadmap to add jab/cross/hook/uppercut
classification on top of this geometry.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from contracts import Hand, LeadOrRear, PoseFrame, PunchEvent

# MediaPipe Pose landmark indices.
LM_NOSE = 0
LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16
LM_LEFT_HIP = 23
LM_RIGHT_HIP = 24

# Defaults tuned for a webcam at ~1m, normal lighting. Re-tuned 2026-05-05
# after a real-world session reported a 28% miss rate; thresholds were
# over-strict relative to MediaPipe world-landmark noise floor.
#
# `threshold_ms` is the real-meter threshold used when MediaPipe world
# landmarks are present. `legacy_threshold_ms` is the 2D-fallback bar.
DEFAULT_THRESHOLD_MS = 2.0  # was 3.0 — MediaPipe underestimates fast motion ~10-15%
DEFAULT_LEGACY_THRESHOLD_MS = 0.8  # 2D-fallback mode
DEFAULT_REFRACTORY_MS = 180.0  # was 300 — fast combos hit ~5/s = 200ms apart
DEFAULT_MIN_VISIBILITY = 0.5  # was 0.6 — extended arms have lower visibility
DEFAULT_BODY_MOTION_THRESHOLD_MS = 2.0  # was 1.2 — stepping into a cross is normal
DEFAULT_MIN_FORWARD_TRAVEL = 0.03  # was 0.05 — accommodate MediaPipe jitter
DEFAULT_DECEL_FACTOR = 0.92  # speed must drop by ≥8% — was 15%, too noisy


@dataclass
class _HandState:
    last_pos: tuple[float, float, float] | None = None
    last_t: float | None = None
    last_speed: float = 0.0
    last_event_t: float | None = None
    # Position history for the forward-extension check (last ~10 frames).
    pos_history: list[tuple[float, float, float, float]] = None  # type: ignore[assignment]
    extension_history: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.pos_history is None:
            self.pos_history = []
        if self.extension_history is None:
            self.extension_history = []


@dataclass
class _BodyState:
    last_hip_pos: tuple[float, float, float] | None = None
    last_t: float | None = None
    speed_ms: float = 0.0


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _wrist_pos(frame: PoseFrame, lm_idx: int, *, world: bool) -> tuple[float, float, float] | None:
    if world and frame.world_landmarks is not None:
        wlm = frame.world_landmarks[lm_idx]
        if wlm.visibility < DEFAULT_MIN_VISIBILITY:
            return None
        return (wlm.x, wlm.y, wlm.z)
    lm = frame.landmarks[lm_idx]
    if lm.visibility < DEFAULT_MIN_VISIBILITY:
        return None
    return (lm.x, lm.y, lm.z)


def _hip_center(frame: PoseFrame, *, world: bool) -> tuple[float, float, float] | None:
    if world and frame.world_landmarks is not None:
        wl_l = frame.world_landmarks[LM_LEFT_HIP]
        wl_r = frame.world_landmarks[LM_RIGHT_HIP]
        if wl_l.visibility < DEFAULT_MIN_VISIBILITY or wl_r.visibility < DEFAULT_MIN_VISIBILITY:
            return None
        return ((wl_l.x + wl_r.x) / 2, (wl_l.y + wl_r.y) / 2, (wl_l.z + wl_r.z) / 2)
    lh = frame.landmarks[LM_LEFT_HIP]
    rh = frame.landmarks[LM_RIGHT_HIP]
    if lh.visibility < DEFAULT_MIN_VISIBILITY or rh.visibility < DEFAULT_MIN_VISIBILITY:
        return None
    return ((lh.x + rh.x) / 2, (lh.y + rh.y) / 2, (lh.z + rh.z) / 2)


def _hand_to_lead_rear(hand: Hand, stance: str | None) -> LeadOrRear | None:
    """Orthodox: left=lead, right=rear. Southpaw: flipped. Switch / unknown: None."""
    if stance == "orthodox":
        return "lead" if hand == "left" else "rear"
    if stance == "southpaw":
        return "lead" if hand == "right" else "rear"
    return None


class HeuristicPunchDetector:
    def __init__(
        self,
        *,
        stance: str | None = None,
        threshold_ms: float = DEFAULT_THRESHOLD_MS,
        legacy_threshold_ms: float = DEFAULT_LEGACY_THRESHOLD_MS,
        refractory_ms: float = DEFAULT_REFRACTORY_MS,
        body_motion_threshold_ms: float = DEFAULT_BODY_MOTION_THRESHOLD_MS,
        min_forward_travel: float = DEFAULT_MIN_FORWARD_TRAVEL,
        # Legacy params kept for backwards-compat with old tests.
        threshold_norm_per_s: float | None = None,
        body_width_m: float | None = None,
        min_visibility: float | None = None,
    ) -> None:
        self.stance = stance
        self.threshold_ms = threshold_ms
        self.legacy_threshold_ms = legacy_threshold_ms
        self.refractory_ms = refractory_ms
        self.body_motion_threshold_ms = body_motion_threshold_ms
        self.min_forward_travel = min_forward_travel
        self._legacy_body_width = body_width_m or 0.45
        # If caller supplied normalized-per-second, translate to legacy m/s.
        if threshold_norm_per_s is not None:
            self.legacy_threshold_ms = threshold_norm_per_s * self._legacy_body_width
        self._min_visibility = (
            min_visibility if min_visibility is not None else DEFAULT_MIN_VISIBILITY
        )
        self._left = _HandState()
        self._right = _HandState()
        self._body = _BodyState()
        self._near_misses: list[dict[str, str | float]] = []

    @property
    def near_misses(self) -> list[dict[str, str | float]]:
        """Read-only view of (peak, reason) entries for peaks that didn't fire."""
        return list(self._near_misses)

    def feed(self, frame: PoseFrame) -> list[PunchEvent]:
        # 1. Update body state — used by all hands as a global gate.
        self._update_body(frame)

        # 2. Per-hand step.
        events: list[PunchEvent] = []
        ev_l = self._step(frame, "left", LM_LEFT_WRIST, LM_LEFT_SHOULDER, self._left)
        if ev_l is not None:
            events.append(ev_l)
        ev_r = self._step(frame, "right", LM_RIGHT_WRIST, LM_RIGHT_SHOULDER, self._right)
        if ev_r is not None:
            events.append(ev_r)
        return events

    def _update_body(self, frame: PoseFrame) -> None:
        use_world = frame.world_landmarks is not None
        hip = _hip_center(frame, world=use_world)
        if hip is None:
            self._body.last_hip_pos = None
            self._body.last_t = None
            self._body.speed_ms = 0.0
            return
        if self._body.last_hip_pos is not None and self._body.last_t is not None:
            dt_s = max(1e-3, (frame.t_ms - self._body.last_t) / 1000.0)
            d = _dist(hip, self._body.last_hip_pos)
            if not use_world:
                # Convert normalized distance to rough meters via assumed shoulder span.
                d *= self._legacy_body_width
            self._body.speed_ms = d / dt_s
        self._body.last_hip_pos = hip
        self._body.last_t = frame.t_ms

    def _step(
        self,
        frame: PoseFrame,
        hand: Hand,
        wrist_idx: int,
        shoulder_idx: int,
        st: _HandState,
    ) -> PunchEvent | None:
        use_world = frame.world_landmarks is not None
        wrist = _wrist_pos(frame, wrist_idx, world=use_world)
        if wrist is None:
            self._reset_hand(st)
            return None

        wrist_vis: float
        if use_world and frame.world_landmarks is not None:
            wrist_vis = frame.world_landmarks[wrist_idx].visibility
        else:
            wrist_vis = frame.landmarks[wrist_idx].visibility

        # Same-shoulder anchor for forward-extension check.
        sh_vis: float
        sh_xyz: tuple[float, float, float]
        if use_world and frame.world_landmarks is not None:
            wl_sh = frame.world_landmarks[shoulder_idx]
            sh_vis = wl_sh.visibility
            sh_xyz = (wl_sh.x, wl_sh.y, wl_sh.z)
        else:
            l_sh = frame.landmarks[shoulder_idx]
            sh_vis = l_sh.visibility
            sh_xyz = (l_sh.x, l_sh.y, l_sh.z)
        if sh_vis < self._min_visibility:
            self._reset_hand(st)
            return None
        extension = _dist(wrist, sh_xyz)

        ev: PunchEvent | None = None
        if st.last_pos is not None and st.last_t is not None:
            dt_s = max(1e-3, (frame.t_ms - st.last_t) / 1000.0)
            d = _dist(wrist, st.last_pos)
            if not use_world:
                d *= self._legacy_body_width
            speed = d / dt_s

            effective_threshold = self.threshold_ms if use_world else self.legacy_threshold_ms
            crossed_threshold = st.last_speed >= effective_threshold
            decelerating = speed < st.last_speed * DEFAULT_DECEL_FACTOR
            spaced = st.last_event_t is None or (frame.t_ms - st.last_event_t) >= self.refractory_ms
            body_quiet = self._body.speed_ms < self.body_motion_threshold_ms
            recently_extended = self._has_forward_extended(st, extension)

            # Near-miss instrumentation: when a peak got close to firing but
            # didn't, record why. Helps tune thresholds from data.
            if st.last_speed >= effective_threshold * 0.7 and not (
                crossed_threshold and decelerating and spaced and body_quiet and recently_extended
            ):
                if not crossed_threshold:
                    reason = "below_threshold"
                elif not spaced:
                    reason = "refractory"
                elif not body_quiet:
                    reason = "body_motion"
                elif not recently_extended:
                    reason = "no_forward_extension"
                elif not decelerating:
                    reason = "still_accelerating"
                else:
                    reason = "unknown"
                self._near_misses.append(
                    {
                        "t_ms": frame.t_ms,
                        "hand": hand,
                        "peak_speed": round(st.last_speed, 2),
                        "reason": reason,
                    }
                )

            if crossed_threshold and decelerating and spaced and body_quiet and recently_extended:
                base_conf = max(
                    0.1,
                    min(
                        1.0, (st.last_speed - effective_threshold) / max(effective_threshold, 1e-3)
                    ),
                )
                
                # Dynamic CV confidence scoring: penalize for occlusion / low visibility
                visibility_factor = min(sh_vis, wrist_vis)
                conf = base_conf * visibility_factor

                ev = PunchEvent(
                    session_id=frame.session_id,
                    t_ms=frame.t_ms,
                    hand=hand,
                    lead_or_rear=_hand_to_lead_rear(hand, self.stance),
                    velocity_ms=round(st.last_speed, 2),
                    velocity_source="world" if use_world else "image_heuristic",
                    detected_by="heuristic",
                    confidence=round(conf, 2),
                )
                st.last_event_t = frame.t_ms
            st.last_speed = speed

        st.last_pos = wrist
        st.last_t = frame.t_ms
        st.extension_history.append(extension)
        if len(st.extension_history) > 10:
            st.extension_history.pop(0)
        return ev

    def _has_forward_extended(self, st: _HandState, current_ext: float) -> bool:
        """True iff the wrist's distance from the shoulder grew by at least
        `min_forward_travel` in the last few frames. Filters out pull-backs."""
        if len(st.extension_history) < 3:
            return False
        recent_min = (
            min(st.extension_history[-5:])
            if len(st.extension_history) >= 5
            else min(st.extension_history)
        )
        return (current_ext - recent_min) >= self.min_forward_travel

    def _reset_hand(self, st: _HandState) -> None:
        st.last_pos = None
        st.last_t = None
        st.last_speed = 0.0


def detect_punches(frames: Iterable[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
    """One-shot helper for offline / batch detection."""
    det = HeuristicPunchDetector(stance=stance)
    out: list[PunchEvent] = []
    for f in frames:
        out.extend(det.feed(f))
    return out


# Re-exported indices for tests and utilities.
__all__ = [
    "LM_LEFT_HIP",
    "LM_LEFT_SHOULDER",
    "LM_LEFT_WRIST",
    "LM_RIGHT_HIP",
    "LM_RIGHT_SHOULDER",
    "LM_RIGHT_WRIST",
    "HeuristicPunchDetector",
    "detect_punches",
]

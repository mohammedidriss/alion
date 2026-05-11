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
LM_LEFT_ELBOW = 13
LM_RIGHT_ELBOW = 14
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
DEFAULT_THRESHOLD_MS = 1.2  # was 2.0 — real jabs register ~1.5 m/s in MediaPipe world coords
DEFAULT_LEGACY_THRESHOLD_MS = 0.5  # 2D-fallback mode (was 0.8)
# Rest-gate parameters. When the fighter is standing still, MediaPipe
# subpixel jitter fakes wrist "movements" that pass the velocity bar
# and produce false positives (we saw 8 fake punches on a no-movement
# session). Track recent body speed; if it stays below
# `rest_body_speed_ms` for `rest_window_s` of history, raise the
# wrist threshold by `rest_threshold_factor` so only a real, large
# movement clears the bar.
DEFAULT_REST_WINDOW_S = 2.0  # was 1.0 — need longer stillness before triggering rest gate
DEFAULT_REST_BODY_SPEED_MS = 0.05  # was 0.10 — stricter: only truly still triggers rest mode
DEFAULT_REST_THRESHOLD_FACTOR = 1.8  # was 2.5 — less aggressive multiplier
DEFAULT_REFRACTORY_MS = 150.0  # was 180 — fast combos hit ~6/s = 167ms apart
DEFAULT_MIN_VISIBILITY = 0.5  # was 0.6 — extended arms have lower visibility
DEFAULT_BODY_MOTION_THRESHOLD_MS = 2.0  # was 1.2 — stepping into a cross is normal
DEFAULT_MIN_FORWARD_TRAVEL = 0.015  # was 0.03 — hooks have minimal forward travel
DEFAULT_DECEL_FACTOR = 0.97  # speed must drop by ≥3% — was 8%, missed fast combos at 30fps
# Elbow-angle gate: at the moment a peak fires, the elbow must have opened
# at least this much (degrees). Set permissively by default — strict
# gates rejected too many real punches in live testing on 2026-05-09.
# Tighten on a per-fighter basis once we have labeled data.
DEFAULT_MIN_ELBOW_ANGLE_DEG = 60.0  # was 80; hooks ~90°, blocks <50°
# Start-from-guard ratio: a real punch starts compact (wrist near
# shoulder) and ends extended. Permissive default for the same reason.
DEFAULT_MIN_EXTENSION_RATIO = 1.02  # was 1.05 — even slight extension counts
# Chambered → extended state-machine. A jab/cross is only legitimate if
# the elbow was bent (≤ chambered_max_deg) within the last
# punch_window_ms, then opened past extended_min_deg at the firing
# frame. Hooks/uppercuts keep the elbow well below extended_min_deg —
# the gate skips them so they aren't penalised.
DEFAULT_CHAMBERED_MAX_DEG = 110.0  # arm "bent" anchor; permissive
DEFAULT_EXTENDED_MIN_DEG = 150.0  # arm "straight" anchor for jab/cross
DEFAULT_PUNCH_WINDOW_MS = 600.0  # max time from chamber to full extension


@dataclass
class _HandState:
    last_pos: tuple[float, float, float] | None = None
    last_t: float | None = None
    last_speed: float = 0.0
    last_event_t: float | None = None
    # Position history for the forward-extension check (last ~10 frames).
    pos_history: list[tuple[float, float, float, float]] = None  # type: ignore[assignment]
    extension_history: list[float] = None  # type: ignore[assignment]
    # State-machine timestamps. `last_chambered_t` is the most recent
    # frame where the elbow angle was below `chambered_max_deg`. Used
    # by the chambered→extended gate to confirm a real jab/cross
    # cycle rather than a fast straight-arm sweep.
    last_chambered_t: float | None = None

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
    # Rolling history of hip-centre speeds (~last 1 s). Used by the
    # rest gate: if the body has been still for the whole window, the
    # detector raises the wrist-velocity bar to ignore MediaPipe
    # subpixel jitter that fakes a "fast" wrist movement.
    speed_history: list[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.speed_history is None:
            self.speed_history = []


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _elbow_angle_deg(
    shoulder: tuple[float, float, float],
    elbow: tuple[float, float, float],
    wrist: tuple[float, float, float],
) -> float:
    """Angle at the elbow joint, in degrees (180° = straight arm)."""
    ux = shoulder[0] - elbow[0]
    uy = shoulder[1] - elbow[1]
    uz = shoulder[2] - elbow[2]
    vx = wrist[0] - elbow[0]
    vy = wrist[1] - elbow[1]
    vz = wrist[2] - elbow[2]
    nu = math.sqrt(ux * ux + uy * uy + uz * uz)
    nv = math.sqrt(vx * vx + vy * vy + vz * vz)
    if nu < 1e-6 or nv < 1e-6:
        return 0.0
    cos_a = max(-1.0, min(1.0, (ux * vx + uy * vy + uz * vz) / (nu * nv)))
    return math.degrees(math.acos(cos_a))


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
        min_elbow_angle_deg: float = DEFAULT_MIN_ELBOW_ANGLE_DEG,
        min_extension_ratio: float = DEFAULT_MIN_EXTENSION_RATIO,
        chambered_max_deg: float = DEFAULT_CHAMBERED_MAX_DEG,
        extended_min_deg: float = DEFAULT_EXTENDED_MIN_DEG,
        punch_window_ms: float = DEFAULT_PUNCH_WINDOW_MS,
        rest_window_s: float = DEFAULT_REST_WINDOW_S,
        rest_body_speed_ms: float = DEFAULT_REST_BODY_SPEED_MS,
        rest_threshold_factor: float = DEFAULT_REST_THRESHOLD_FACTOR,
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
        self.min_elbow_angle_deg = min_elbow_angle_deg
        self.min_extension_ratio = min_extension_ratio
        self.chambered_max_deg = chambered_max_deg
        self.extended_min_deg = extended_min_deg
        self.punch_window_ms = punch_window_ms
        self.rest_window_s = rest_window_s
        self.rest_body_speed_ms = rest_body_speed_ms
        self.rest_threshold_factor = rest_threshold_factor
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
        ev_l = self._step(frame, "left", LM_LEFT_WRIST, LM_LEFT_SHOULDER, LM_LEFT_ELBOW, self._left)
        if ev_l is not None:
            events.append(ev_l)
        ev_r = self._step(
            frame, "right", LM_RIGHT_WRIST, LM_RIGHT_SHOULDER, LM_RIGHT_ELBOW, self._right
        )
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
            # Append to the rolling window used by the rest gate. We
            # don't know fps here, so size the buffer by elapsed time:
            # drop entries older than rest_window_s.
            self._body.speed_history.append(self._body.speed_ms)
            # Cap the buffer at ~120 entries (~4s at 30fps) so it
            # doesn't grow unbounded if frames keep coming.
            if len(self._body.speed_history) > 120:
                self._body.speed_history.pop(0)
        self._body.last_hip_pos = hip
        self._body.last_t = frame.t_ms

    def _is_at_rest(self) -> bool:
        """True iff the body has been essentially still for the whole
        rolling window. Used to multiply the wrist-velocity threshold
        and reject MediaPipe-jitter false positives on still video."""
        hist = self._body.speed_history
        # Need a populated window; otherwise treat as 'not resting'
        # (default behaviour).
        if len(hist) < 60:
            return False
        # Use the recent tail (~2s of frames assuming 30fps).
        # Need a longer window to avoid false rest during natural
        # pauses between combos.
        recent = hist[-60:] if len(hist) >= 60 else hist
        max_speed = max(recent)
        return max_speed < self.rest_body_speed_ms

    def _step(
        self,
        frame: PoseFrame,
        hand: Hand,
        wrist_idx: int,
        shoulder_idx: int,
        elbow_idx: int,
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

        # Elbow keypoint — required for the elbow-angle gate.
        if use_world and frame.world_landmarks is not None:
            wl_el = frame.world_landmarks[elbow_idx]
            elbow_vis = wl_el.visibility
            elbow_xyz: tuple[float, float, float] = (wl_el.x, wl_el.y, wl_el.z)
        else:
            l_el = frame.landmarks[elbow_idx]
            elbow_vis = l_el.visibility
            elbow_xyz = (l_el.x, l_el.y, l_el.z)
        elbow_ok = elbow_vis >= self._min_visibility
        elbow_angle = _elbow_angle_deg(sh_xyz, elbow_xyz, wrist) if elbow_ok else 180.0

        extension = _dist(wrist, sh_xyz)

        ev: PunchEvent | None = None
        if st.last_pos is not None and st.last_t is not None:
            dt_s = max(1e-3, (frame.t_ms - st.last_t) / 1000.0)
            d = _dist(wrist, st.last_pos)
            if not use_world:
                d *= self._legacy_body_width
            speed = d / dt_s

            base_threshold = self.threshold_ms if use_world else self.legacy_threshold_ms
            # Rest gate is now a SOFT penalty (confidence reduction) rather
            # than a hard threshold multiplier. This prevents the rest gate
            # from killing all detection in later rounds of a multi-round
            # session where rest periods cause the gate to latch.
            at_rest = self._is_at_rest()

            # --- 3 HARD gates (must ALL pass to fire) ---
            crossed_threshold = st.last_speed >= base_threshold
            decelerating = speed < st.last_speed * DEFAULT_DECEL_FACTOR
            spaced = st.last_event_t is None or (frame.t_ms - st.last_event_t) >= self.refractory_ms

            # --- 5 SOFT gates (reduce confidence but don't block) ---
            body_quiet = self._body.speed_ms < self.body_motion_threshold_ms
            recently_extended = self._has_forward_extended(st, extension)
            elbow_open_enough = elbow_angle <= 0.0 or elbow_angle >= self.min_elbow_angle_deg
            extension_ratio_ok = self._extension_ratio_ok(st, extension)
            if elbow_angle >= self.extended_min_deg:
                chambered_recently = (
                    st.last_chambered_t is not None
                    and (frame.t_ms - st.last_chambered_t) <= self.punch_window_ms
                )
            else:
                chambered_recently = True

            # Near-miss instrumentation (only for hard gate failures).
            if st.last_speed >= base_threshold * 0.7 and not (
                crossed_threshold and decelerating and spaced
            ):
                if not crossed_threshold:
                    reason = "below_threshold"
                elif not spaced:
                    reason = "refractory"
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

            if crossed_threshold and decelerating and spaced:
                # Start with velocity-based confidence.
                base_conf = max(
                    0.1,
                    min(
                        1.0, (st.last_speed - base_threshold) / max(base_threshold, 1e-3)
                    ),
                )

                # Apply soft gate penalties — each failed soft gate reduces
                # confidence by a fraction, but never blocks the detection.
                soft_penalty = 1.0
                if at_rest:
                    soft_penalty *= 0.5  # might be jitter, halve confidence
                if not body_quiet:
                    soft_penalty *= 0.7  # whole body moving, could be footwork
                if not recently_extended:
                    soft_penalty *= 0.8  # no clear forward extension
                if not elbow_open_enough:
                    soft_penalty *= 0.8  # elbow too bent for a clean punch
                if not extension_ratio_ok:
                    soft_penalty *= 0.8  # arm didn't clearly extend
                if not chambered_recently:
                    soft_penalty *= 0.8  # no chamber-to-extend cycle

                # Visibility penalty.
                visibility_factor = min(sh_vis, wrist_vis)
                conf = base_conf * soft_penalty * visibility_factor

                ev = PunchEvent(
                    session_id=frame.session_id,
                    t_ms=frame.t_ms,
                    hand=hand,
                    lead_or_rear=_hand_to_lead_rear(hand, self.stance),
                    velocity_ms=round(st.last_speed, 2),
                    velocity_source="world" if use_world else "image_heuristic",
                    detected_by="heuristic",
                    confidence=round(max(0.05, conf), 2),
                )
                st.last_event_t = frame.t_ms
            st.last_speed = speed

        st.last_pos = wrist
        st.last_t = frame.t_ms
        st.extension_history.append(extension)
        if len(st.extension_history) > 10:
            st.extension_history.pop(0)
        # Refresh chamber timestamp whenever the elbow is bent enough.
        # Skip when the angle is degenerate (≈0°, only happens with
        # synthetic 2D test data) so the gate doesn't latch on bogus
        # geometry.
        if elbow_ok and 1.0 < elbow_angle <= self.chambered_max_deg:
            st.last_chambered_t = frame.t_ms
        return ev

    def _extension_ratio_ok(self, st: _HandState, current_ext: float) -> bool:
        """True iff the wrist actually started compact and ended extended.

        Catches the failure mode where MediaPipe jitters fast on a wrist
        that was already extended (e.g. holding hands up, slight hand
        wave). A real punch starts near the shoulder and ends extended.
        """
        if len(st.extension_history) < 4:
            return False
        window_min = min(st.extension_history[-10:])
        # Wrist started at the shoulder (or with degenerate geometry) and
        # ended meaningfully extended — that's an unambiguous punch.
        if window_min < 1e-6:
            return current_ext > 0.05
        return current_ext / window_min >= self.min_extension_ratio

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
    "LM_LEFT_ELBOW",
    "LM_LEFT_HIP",
    "LM_LEFT_SHOULDER",
    "LM_LEFT_WRIST",
    "LM_RIGHT_ELBOW",
    "LM_RIGHT_HIP",
    "LM_RIGHT_SHOULDER",
    "LM_RIGHT_WRIST",
    "HeuristicPunchDetector",
    "detect_punches",
]

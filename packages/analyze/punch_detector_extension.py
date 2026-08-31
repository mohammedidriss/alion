"""Extension-cycle punch detector — precision-first (ADR 009).

The Phase-1 `HeuristicPunchDetector` fires on any wrist-velocity peak that clears
a speed threshold; the geometric "is this actually a punch" checks are only soft
confidence nudges, so incidental hand motion (guard adjustments, sway, jitter)
counts as punches. On a labeled reference session it scored precision ~0.05
(80+ false positives for 4 real punches).

This detector instead counts a punch only on a genuine **extension cycle**: the
wrist travels *out* from a chambered/retracted position to a clear peak
extension and then *retracts*. That out-and-back excursion is what distinguishes
a punch from arbitrary movement, and it is direction-agnostic — it captures
jabs, crosses, hooks, and uppercuts alike (all send the wrist out and back)
without depending on the elbow fully straightening.

Gates (all hard):
- **Excursion amplitude**: peak-minus-chamber wrist travel ≥ `min_excursion_m`.
  Kills jitter and small guard movements.
- **Peak speed**: the outward motion reached ≥ `min_peak_velocity_ms`.
- **Retraction**: the wrist must come back off the peak before the punch counts,
  and must return most of the way before another can — enforces one-per-cycle.
- **Refractory**: minimum time between counts.

Uses MediaPipe world landmarks (metric) when present, else the 2D image plane
scaled by an assumed body width.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, field

from contracts import Hand, LeadOrRear, PoseFrame, PunchEvent

LM_LEFT_SHOULDER = 11
LM_RIGHT_SHOULDER = 12
LM_LEFT_ELBOW = 13
LM_RIGHT_ELBOW = 14
LM_LEFT_WRIST = 15
LM_RIGHT_WRIST = 16

# The wrist-excursion gate catches wide/side punches (hooks, and anything moving
# across the image plane). But a straight punch thrown *toward the camera* travels
# along the depth axis, which a monocular camera estimates poorly — its measured
# speed/travel are compressed, so the excursion gate misses it. The elbow-extension
# gate is direction-invariant: a jab/cross straightens the elbow no matter which
# way the fighter faces, so a fast chamber→extend of the elbow counts as a punch
# even when the wrist's forward motion is invisible. Hooks/uppercuts never fully
# straighten, so they are left to the excursion gate. See ADR 009.
DEFAULT_MIN_PEAK_VELOCITY_MS = 2.5  # was 1.2 (far too low); 3.0 under-caught depth-axis punches
DEFAULT_MIN_EXCURSION_M = 0.04  # min wrist travel valley→peak, metres (world coords)
DEFAULT_HYSTERESIS_M = 0.03  # turn-around must exceed this to confirm a peak/valley
DEFAULT_REFRACTORY_MS = 250.0
DEFAULT_MIN_VISIBILITY = 0.5
DEFAULT_LEGACY_BODY_WIDTH_M = 0.45  # 2D-fallback scale (no world landmarks)
# Elbow-extension gate.
DEFAULT_ELBOW_CHAMBER_DEG = 100.0  # elbow counts as "bent" below this
DEFAULT_ELBOW_EXTEND_DEG = 150.0  # ...and "straight" above this
DEFAULT_ELBOW_WINDOW_MS = 200.0  # bent→straight must happen within this window (punch tempo)


@dataclass
class _HandCycle:
    """Per-hand state: wrist-excursion hysteresis tracker + elbow-extension tracker."""

    going_up: bool = True
    extreme: float | None = None  # current local extreme (peak while up, valley while down)
    chamber: float | None = None  # last confirmed valley — the excursion baseline
    rise_peak_speed: float = 0.0
    peak_t: float = 0.0
    last_pos: tuple[float, float, float] | None = None
    last_t: float | None = None
    last_event_t: float | None = None  # shared refractory across both gates
    # Elbow-extension gate: recent (t_ms, angle) samples for the tempo window.
    elbow_hist: list[tuple[float, float]] = field(default_factory=list)
    elbow_extended: bool = False  # currently past the extend threshold — needs re-chamber


def _dist(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _elbow_angle_deg(
    shoulder: tuple[float, float, float],
    elbow: tuple[float, float, float],
    wrist: tuple[float, float, float],
) -> float:
    """Angle at the elbow joint in degrees (180° = fully straight arm)."""
    ux, uy, uz = (shoulder[i] - elbow[i] for i in range(3))
    vx, vy, vz = (wrist[i] - elbow[i] for i in range(3))
    nu = math.sqrt(ux * ux + uy * uy + uz * uz)
    nv = math.sqrt(vx * vx + vy * vy + vz * vz)
    if nu < 1e-6 or nv < 1e-6:
        return 180.0
    cos_a = max(-1.0, min(1.0, (ux * vx + uy * vy + uz * vz) / (nu * nv)))
    return math.degrees(math.acos(cos_a))


def _hand_to_lead_rear(hand: Hand, stance: str | None) -> LeadOrRear | None:
    if stance == "orthodox":
        return "lead" if hand == "left" else "rear"
    if stance == "southpaw":
        return "lead" if hand == "right" else "rear"
    return None


@dataclass
class ExtensionCyclePunchDetector:
    """Streaming detector — feed `PoseFrame`s, get `PunchEvent`s on completed cycles.

    Tracks the wrist→shoulder extension as a signal and, with hysteresis, finds
    each local peak and the valley (chamber) that preceded it. A peak becomes a
    punch when the outward motion into it was ballistic (peak speed ≥ threshold)
    and travelled a real distance (amplitude ≥ min_excursion). One count per
    peak, gated by a refractory window.
    """

    stance: str | None = None
    min_peak_velocity_ms: float = DEFAULT_MIN_PEAK_VELOCITY_MS
    min_excursion_m: float = DEFAULT_MIN_EXCURSION_M
    hysteresis_m: float = DEFAULT_HYSTERESIS_M
    refractory_ms: float = DEFAULT_REFRACTORY_MS
    min_visibility: float = DEFAULT_MIN_VISIBILITY
    body_width_m: float = DEFAULT_LEGACY_BODY_WIDTH_M
    elbow_chamber_deg: float = DEFAULT_ELBOW_CHAMBER_DEG
    elbow_extend_deg: float = DEFAULT_ELBOW_EXTEND_DEG
    elbow_window_ms: float = DEFAULT_ELBOW_WINDOW_MS

    _left: _HandCycle = field(default_factory=_HandCycle, init=False)
    _right: _HandCycle = field(default_factory=_HandCycle, init=False)

    @property
    def near_misses(self) -> list[dict[str, str | float]]:
        """Drop-in parity with HeuristicPunchDetector; this detector keeps none."""
        return []

    def feed(self, frame: PoseFrame) -> list[PunchEvent]:
        events: list[PunchEvent] = []
        ev_l = self._step(
            frame, "left", LM_LEFT_WRIST, LM_LEFT_SHOULDER, LM_LEFT_ELBOW, self._left
        )
        if ev_l is not None:
            events.append(ev_l)
        ev_r = self._step(
            frame, "right", LM_RIGHT_WRIST, LM_RIGHT_SHOULDER, LM_RIGHT_ELBOW, self._right
        )
        if ev_r is not None:
            events.append(ev_r)
        return events

    def _landmark(
        self, frame: PoseFrame, idx: int, *, world: bool
    ) -> tuple[tuple[float, float, float], float] | None:
        lm = (
            frame.world_landmarks[idx]
            if (world and frame.world_landmarks)
            else frame.landmarks[idx]
        )
        if lm.visibility < self.min_visibility:
            return None
        return (lm.x, lm.y, lm.z), lm.visibility

    def _step(
        self,
        frame: PoseFrame,
        hand: Hand,
        wrist_idx: int,
        shoulder_idx: int,
        elbow_idx: int,
        cyc: _HandCycle,
    ) -> PunchEvent | None:
        use_world = frame.world_landmarks is not None
        wrist = self._landmark(frame, wrist_idx, world=use_world)
        shoulder = self._landmark(frame, shoulder_idx, world=use_world)
        if wrist is None or shoulder is None:
            cyc.last_pos = None
            cyc.last_t = None
            return None

        (wx, wy, wz), wrist_vis = wrist
        (sx, sy, sz), sh_vis = shoulder
        wrist_xyz = (wx, wy, wz)
        scale = 1.0 if use_world else self.body_width_m
        ext = _dist(wrist_xyz, (sx, sy, sz)) * scale

        speed = 0.0
        if cyc.last_pos is not None and cyc.last_t is not None:
            dt_s = max(1e-3, (frame.t_ms - cyc.last_t) / 1000.0)
            speed = _dist(wrist_xyz, cyc.last_pos) * scale / dt_s
        cyc.last_pos = wrist_xyz
        cyc.last_t = frame.t_ms

        # Bootstrap on the first valid frame.
        if cyc.extreme is None or cyc.chamber is None:
            cyc.extreme = ext
            cyc.chamber = ext
            cyc.peak_t = frame.t_ms
            return None

        ev: PunchEvent | None = None

        if cyc.going_up:
            if ext > cyc.extreme:
                cyc.extreme = ext
                cyc.peak_t = frame.t_ms
            cyc.rise_peak_speed = max(cyc.rise_peak_speed, speed)
            # Confirmed turn-around: the peak we were tracking is a local maximum.
            if ext <= cyc.extreme - self.hysteresis_m:
                amplitude = cyc.extreme - cyc.chamber
                spaced = (
                    cyc.last_event_t is None
                    or (cyc.peak_t - cyc.last_event_t) >= self.refractory_ms
                )
                if (
                    amplitude >= self.min_excursion_m
                    and cyc.rise_peak_speed >= self.min_peak_velocity_ms
                    and spaced
                ):
                    ev = PunchEvent(
                        session_id=frame.session_id,
                        t_ms=cyc.peak_t,
                        hand=hand,
                        lead_or_rear=_hand_to_lead_rear(hand, self.stance),
                        velocity_ms=round(cyc.rise_peak_speed, 2),
                        velocity_source="world" if use_world else "image_heuristic",
                        detected_by="heuristic",
                        confidence=round(
                            _confidence(
                                amplitude,
                                cyc.rise_peak_speed,
                                self.min_excursion_m,
                                self.min_peak_velocity_ms,
                                min(sh_vis, wrist_vis),
                            ),
                            2,
                        ),
                    )
                    cyc.last_event_t = cyc.peak_t
                cyc.going_up = False
                cyc.extreme = ext  # start tracking the following valley
        else:  # tracking a valley
            if ext < cyc.extreme:
                cyc.extreme = ext
            # Confirmed turn-around: the valley we were tracking is a local minimum.
            if ext >= cyc.extreme + self.hysteresis_m:
                cyc.chamber = cyc.extreme  # this valley is the next punch's baseline
                cyc.going_up = True
                cyc.extreme = ext
                cyc.rise_peak_speed = speed
                cyc.peak_t = frame.t_ms

        # --- Elbow-extension gate: fires when the elbow goes from bent to straight
        # within a short window — a punch tempo. Direction-invariant, so it catches
        # straight punches thrown toward the camera that the excursion gate misses.
        elbow = self._landmark(frame, elbow_idx, world=use_world)
        if elbow is not None:
            elbow_angle = _elbow_angle_deg((sx, sy, sz), elbow[0], wrist_xyz)
            cyc.elbow_hist.append((frame.t_ms, elbow_angle))
            cutoff = frame.t_ms - self.elbow_window_ms
            cyc.elbow_hist = [(t, a) for (t, a) in cyc.elbow_hist if t >= cutoff]
            if elbow_angle <= self.elbow_chamber_deg:
                cyc.elbow_extended = False  # re-armed
            recent_min = min(a for _, a in cyc.elbow_hist)
            if (
                not cyc.elbow_extended
                and elbow_angle >= self.elbow_extend_deg
                and recent_min <= self.elbow_chamber_deg  # was bent within the window
            ):
                spaced = (
                    cyc.last_event_t is None
                    or (frame.t_ms - cyc.last_event_t) >= self.refractory_ms
                )
                if ev is None and spaced:
                    ev = PunchEvent(
                        session_id=frame.session_id,
                        t_ms=frame.t_ms,
                        hand=hand,
                        lead_or_rear=_hand_to_lead_rear(hand, self.stance),
                        velocity_ms=round(speed, 2),
                        velocity_source="world" if use_world else "image_heuristic",
                        detected_by="heuristic",
                        confidence=0.6,
                    )
                    cyc.last_event_t = frame.t_ms
                cyc.elbow_extended = True  # require re-chamber before the next elbow fire

        return ev


def _confidence(
    amplitude: float,
    peak_speed: float,
    min_excursion: float,
    min_velocity: float,
    visibility: float,
) -> float:
    """0.05–1.0 from how decisively the excursion and speed cleared their floors."""
    amp_term = min(1.0, amplitude / (min_excursion * 2.0))
    spd_term = min(1.0, peak_speed / (min_velocity * 1.6))
    return max(0.05, min(1.0, 0.5 * amp_term + 0.5 * spd_term) * max(0.2, visibility))


def detect_punches_extension(
    frames: Iterable[PoseFrame], *, stance: str | None = None
) -> list[PunchEvent]:
    """One-shot helper for offline / batch detection."""
    det = ExtensionCyclePunchDetector(stance=stance)
    out: list[PunchEvent] = []
    for f in frames:
        out.extend(det.feed(f))
    return out

"""Heuristic punch-type classifier (jab / cross / hook / uppercut).

This is a v0.5 classifier that runs *after* the existing
HeuristicPunchDetector has already decided "yes, a punch happened on this
hand at this time." It looks at the wrist's 3D trajectory in the few frames
leading up to the detection and labels the punch type from the dominant
motion axis + the relationship to the fighter's stance.

It's intentionally crude. The Phase 3 LSTM replaces this with a learned
model on the same `PunchEvent.punch_type` field — the consumer-facing
contract doesn't change between heuristic-v0.5 and lstm_v1.

Heuristic in plain English (with `world` 3D coordinates, hip-centered):
- z is depth (positive = away from camera, the "punching forward" axis)
- x is sideways (positive = subject's right)
- y is vertical (positive = down in image space, but world frame is hip-centered)

Decision tree:
1. If wrist moves up significantly more than forward/sideways → uppercut.
2. Else if the lateral motion (|Δx|) is bigger than forward (|Δz|) → hook.
3. Else (forward motion dominant) → jab if the punching hand is the
   fighter's lead hand, cross if it's the rear hand. Without a known
   stance, we tag both straight punches as `jab` (the default lead).

Returns None if there isn't enough trajectory context to classify, which
keeps the existing PunchEvent flow working when world landmarks are absent.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from analyze.punch_detector_heuristic import (
    LM_LEFT_WRIST,
    LM_RIGHT_WRIST,
)
from contracts import Hand, PoseFrame

PunchType = Literal["jab", "cross", "hook", "uppercut"]


# Defaults (in meters when world landmarks are present, normalized otherwise).
# Lateral threshold: how much sideways travel must dominate forward to call it a hook.
HOOK_LATERAL_RATIO = 1.2  # |Δx| / |Δz| ≥ 1.2 → hook
UPPERCUT_VERTICAL_RATIO = 1.4  # upward Δy must dominate by this much
TRAJECTORY_FRAMES = 5  # frames to look back when reading the trajectory


def classify_punch_type(
    pose_history: Sequence[PoseFrame],
    hand: Hand,
    stance: str | None,
    *,
    lookback: int = TRAJECTORY_FRAMES,
) -> PunchType | None:
    """Look at the last `lookback` frames of pose history and return a punch type.

    `pose_history` should be the rolling buffer of recent PoseFrames the
    capture pipeline has produced (newest last). Returns None when context
    is insufficient (too few frames, or wrist visibility too low).
    """
    if len(pose_history) < 2:
        return None

    # Take the tail and find a stable starting frame for the trajectory.
    tail = list(pose_history[-lookback:])
    if len(tail) < 2:
        return None

    wrist_idx = LM_LEFT_WRIST if hand == "left" else LM_RIGHT_WRIST

    # Prefer world landmarks (real metres). Fall back to image-plane.
    use_world = all(f.world_landmarks is not None for f in tail)

    def wrist_xyz(f: PoseFrame) -> tuple[float, float, float] | None:
        if use_world and f.world_landmarks is not None:
            wlm = f.world_landmarks[wrist_idx]
            if wlm.visibility < 0.4:
                return None
            return (wlm.x, wlm.y, wlm.z)
        lm = f.landmarks[wrist_idx]
        if lm.visibility < 0.4:
            return None
        return (lm.x, lm.y, lm.z)

    start = wrist_xyz(tail[0])
    end = wrist_xyz(tail[-1])
    if start is None or end is None:
        return None

    dx = end[0] - start[0]  # lateral
    dy = end[1] - start[1]  # vertical (negative = upward in image; world = downward usually)
    dz = end[2] - start[2]  # depth (forward when negative if the camera looks at +z?)

    # MediaPipe world: +y is roughly "downward away from face." A punch upward
    # toward the target produces a *negative* Δy (wrist rises). Take absolute
    # |Δy| and check sign separately.
    abs_dx = abs(dx)
    abs_dy = abs(dy)
    abs_dz = abs(dz)

    # 1. Uppercut: dominant vertical motion AND it's an upward motion.
    if abs_dy >= UPPERCUT_VERTICAL_RATIO * max(abs_dx, abs_dz, 1e-6) and dy < 0:
        return "uppercut"

    # 2. Hook: lateral motion dominates forward.
    if abs_dx >= HOOK_LATERAL_RATIO * max(abs_dz, 1e-6):
        return "hook"

    # 3. Straight punch — jab if lead hand, cross if rear.
    is_lead = (stance == "orthodox" and hand == "left") or (
        stance == "southpaw" and hand == "right"
    )
    if stance in ("orthodox", "southpaw"):
        return "jab" if is_lead else "cross"

    # No known stance: default to "jab" for any straight punch (closer to
    # lead-hand-dominant; the dashboard surfaces stance separately).
    return "jab"

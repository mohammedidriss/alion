"""Punch-type heuristic classifier on synthetic 3D wrist trajectories.

Each test builds a 5-frame trajectory in world coordinates that simulates
one specific punch shape, then asserts the classifier picks the right type.
"""

from __future__ import annotations

from uuid import uuid4

from analyze import classify_punch_type
from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame, WorldLandmark


def _frame(
    sid,  # type: ignore[no-untyped-def]
    idx: int,
    *,
    right_wrist: tuple[float, float, float],
    left_wrist: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> PoseFrame:
    """Build a PoseFrame where left and right wrist world coords are set explicitly.

    All other landmarks have visibility 0 so the classifier doesn't need them.
    """
    image_lms = tuple(
        Landmark(x=0.5, y=0.5, z=0.0, visibility=0.5) for _ in range(NUM_POSE_LANDMARKS)
    )
    world_lms_list = [
        WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=0.0) for _ in range(NUM_POSE_LANDMARKS)
    ]
    # 15 = LM_LEFT_WRIST, 16 = LM_RIGHT_WRIST
    world_lms_list[15] = WorldLandmark(
        x=left_wrist[0], y=left_wrist[1], z=left_wrist[2], visibility=0.95
    )
    world_lms_list[16] = WorldLandmark(
        x=right_wrist[0], y=right_wrist[1], z=right_wrist[2], visibility=0.95
    )
    return PoseFrame(
        session_id=sid,
        frame_index=idx,
        t_ms=idx * 33.33,
        landmarks=image_lms,
        world_landmarks=tuple(world_lms_list),
    )


def test_straight_punch_orthodox_right_is_cross() -> None:
    sid = uuid4()
    # Right wrist moves forward (z grows) without much lateral or vertical motion.
    history = [
        _frame(sid, 0, right_wrist=(0.20, 0.0, -0.30)),
        _frame(sid, 1, right_wrist=(0.20, 0.0, -0.20)),
        _frame(sid, 2, right_wrist=(0.20, 0.0, -0.10)),
        _frame(sid, 3, right_wrist=(0.20, 0.0, 0.05)),
        _frame(sid, 4, right_wrist=(0.20, 0.0, 0.10)),
    ]
    assert classify_punch_type(history, "right", "orthodox") == "cross"


def test_straight_punch_orthodox_left_is_jab() -> None:
    sid = uuid4()
    history = [
        _frame(sid, i, right_wrist=(0.0, 0.0, 0.0), left_wrist=(-0.20, 0.0, -0.30 + i * 0.10))
        for i in range(5)
    ]
    assert classify_punch_type(history, "left", "orthodox") == "jab"


def test_southpaw_flips_jab_and_cross() -> None:
    sid = uuid4()
    history = [_frame(sid, i, right_wrist=(0.20, 0.0, -0.30 + i * 0.10)) for i in range(5)]
    assert classify_punch_type(history, "right", "southpaw") == "jab"


def test_lateral_motion_classifies_as_hook() -> None:
    sid = uuid4()
    # Right wrist sweeps strongly sideways (Δx large) with minimal forward.
    history = [
        _frame(sid, 0, right_wrist=(0.10, 0.0, 0.0)),
        _frame(sid, 1, right_wrist=(0.05, 0.0, 0.01)),
        _frame(sid, 2, right_wrist=(-0.05, 0.0, 0.02)),
        _frame(sid, 3, right_wrist=(-0.20, 0.0, 0.02)),
        _frame(sid, 4, right_wrist=(-0.35, 0.0, 0.02)),
    ]
    assert classify_punch_type(history, "right", "orthodox") == "hook"


def test_upward_motion_classifies_as_uppercut() -> None:
    sid = uuid4()
    # Wrist rises sharply (Δy negative dominates).
    # MediaPipe world: hip-centered, so a punch toward the face → wrist y decreases.
    history = [_frame(sid, i, right_wrist=(0.10, 0.20 - i * 0.10, 0.0)) for i in range(5)]
    assert classify_punch_type(history, "right", "orthodox") == "uppercut"


def test_no_stance_defaults_straight_to_jab() -> None:
    sid = uuid4()
    history = [_frame(sid, i, right_wrist=(0.20, 0.0, -0.30 + i * 0.10)) for i in range(5)]
    assert classify_punch_type(history, "right", None) == "jab"


def test_too_few_frames_returns_none() -> None:
    sid = uuid4()
    assert classify_punch_type([_frame(sid, 0, right_wrist=(0, 0, 0))], "left", "orthodox") is None


def test_low_visibility_returns_none() -> None:
    sid = uuid4()
    # All zeros means visibility=0 in our helper for non-set indices.
    # We need to override the wrist's visibility specifically.
    image_lms = tuple(
        Landmark(x=0.5, y=0.5, z=0.0, visibility=0.5) for _ in range(NUM_POSE_LANDMARKS)
    )
    world_lms_list = [
        WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=0.1)  # below 0.4 threshold
        for _ in range(NUM_POSE_LANDMARKS)
    ]
    pf = PoseFrame(
        session_id=sid,
        frame_index=0,
        t_ms=0.0,
        landmarks=image_lms,
        world_landmarks=tuple(world_lms_list),
    )
    assert classify_punch_type([pf, pf], "left", "orthodox") is None

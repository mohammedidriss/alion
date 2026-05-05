"""Heuristic punch detector — synthetic pose stream, no camera needed."""

from __future__ import annotations

from uuid import uuid4

from analyze import HeuristicPunchDetector
from analyze.punch_detector_heuristic import (
    LM_LEFT_HIP,
    LM_LEFT_SHOULDER,
    LM_LEFT_WRIST,
    LM_RIGHT_HIP,
    LM_RIGHT_SHOULDER,
    LM_RIGHT_WRIST,
)
from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame, WorldLandmark


def _frame(session_id, idx: int, fps: float, lwx: float, rwx: float) -> PoseFrame:  # type: ignore[no-untyped-def]
    """Builds a pose frame; left/right wrist x positions are configurable."""
    landmarks = []
    for i in range(NUM_POSE_LANDMARKS):
        if i == LM_LEFT_WRIST:
            landmarks.append(Landmark(x=lwx, y=0.5, z=0.0, visibility=0.95))
        elif i == LM_RIGHT_WRIST:
            landmarks.append(Landmark(x=rwx, y=0.5, z=0.0, visibility=0.95))
        else:
            landmarks.append(Landmark(x=0.5, y=0.5, z=0.0, visibility=0.95))
    return PoseFrame(
        session_id=session_id,
        frame_index=idx,
        t_ms=(idx / fps) * 1000.0,
        landmarks=tuple(landmarks),
    )


def test_idle_produces_no_events() -> None:
    sid = uuid4()
    det = HeuristicPunchDetector()
    events = []
    for i in range(60):
        events.extend(det.feed(_frame(sid, i, 30.0, 0.3, 0.7)))
    assert events == []


def test_fast_extension_then_decel_emits_event() -> None:
    """Right wrist accelerates from 0.3 → 0.7 over 5 frames @30fps then holds."""
    sid = uuid4()
    det = HeuristicPunchDetector()
    events = []
    positions = [0.30, 0.40, 0.55, 0.68, 0.71, 0.72, 0.72, 0.72]
    for i, x in enumerate(positions):
        events.extend(det.feed(_frame(sid, i, 30.0, 0.3, x)))
    rights = [e for e in events if e.hand == "right"]
    assert len(rights) >= 1
    assert rights[0].detected_by == "heuristic"
    assert rights[0].velocity_ms > 0


def test_walking_body_motion_suppresses_event() -> None:
    """A wrist that moves fast while the entire body is also translating shouldn't count."""
    sid = uuid4()
    det = HeuristicPunchDetector(body_motion_threshold_ms=0.5)
    events = []
    # Whole body marches forward at 0.05 normalized/frame ≈ 1.5 normalized/s
    # × 0.45 body width ≈ 0.675 m/s — over the 0.5 m/s body-motion threshold.
    for i in range(8):
        body_x = 0.3 + i * 0.05
        # Wrist also moves fast (would otherwise trigger).
        rwx = body_x + 0.4
        landmarks = []
        for k in range(NUM_POSE_LANDMARKS):
            if k == LM_RIGHT_WRIST:
                landmarks.append(Landmark(x=rwx, y=0.5, z=0.0, visibility=0.95))
            elif k in (LM_LEFT_HIP, LM_RIGHT_HIP, LM_LEFT_SHOULDER, LM_RIGHT_SHOULDER):
                landmarks.append(Landmark(x=body_x, y=0.5, z=0.0, visibility=0.95))
            else:
                landmarks.append(Landmark(x=body_x, y=0.5, z=0.0, visibility=0.95))
        frame = PoseFrame(
            session_id=sid, frame_index=i, t_ms=(i / 30.0) * 1000.0, landmarks=tuple(landmarks)
        )
        events.extend(det.feed(frame))
    assert events == []


def test_stance_orthodox_labels_lead_and_rear() -> None:
    sid = uuid4()
    det = HeuristicPunchDetector(stance="orthodox")
    positions = [0.30, 0.40, 0.55, 0.68, 0.71, 0.72, 0.72]
    events = []
    for i, x in enumerate(positions):
        events.extend(det.feed(_frame(sid, i, 30.0, 0.3, x)))
    rights = [e for e in events if e.hand == "right"]
    assert rights and rights[0].lead_or_rear == "rear"


def test_world_landmarks_path_emits_metric_velocity_source() -> None:
    """When world landmarks are present, the detector should report velocity_source='world'."""
    sid = uuid4()
    det = HeuristicPunchDetector()  # default 3.0 m/s threshold
    frames: list[PoseFrame] = []
    # Right wrist accelerates from x=0 to x=0.5m over 5 frames at 30fps
    # = 0.5m / 0.167s = ~3 m/s — right at threshold, then we add a higher peak.
    wrist_xs = [0.0, 0.1, 0.25, 0.45, 0.55, 0.55, 0.55]
    for i, wx in enumerate(wrist_xs):
        # Both 2D and world: shoulder at (0,0,0), hip stationary at (0,0,0).
        lm2d = []
        wld = []
        for k in range(NUM_POSE_LANDMARKS):
            if k == LM_RIGHT_WRIST:
                lm2d.append(Landmark(x=0.5 + wx, y=0.5, z=0.0, visibility=0.95))
                wld.append(WorldLandmark(x=wx, y=0.0, z=0.0, visibility=0.95))
            elif k == LM_RIGHT_SHOULDER:
                lm2d.append(Landmark(x=0.5, y=0.5, z=0.0, visibility=0.95))
                wld.append(WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=0.95))
            else:
                lm2d.append(Landmark(x=0.5, y=0.5, z=0.0, visibility=0.95))
                wld.append(WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=0.95))
        frames.append(
            PoseFrame(
                session_id=sid,
                frame_index=i,
                t_ms=(i / 30.0) * 1000.0,
                landmarks=tuple(lm2d),
                world_landmarks=tuple(wld),
            )
        )
    events = []
    for f in frames:
        events.extend(det.feed(f))
    assert events, "expected at least one detection in world-landmark path"
    assert events[0].velocity_source == "world"
    # Velocity should be in real m/s — peak speed was ~6 m/s (0.20m in 0.033s).
    assert events[0].velocity_ms >= 3.0


def test_refractory_blocks_second_event_too_soon() -> None:
    sid = uuid4()
    det = HeuristicPunchDetector(refractory_ms=400.0)
    events = []
    # Two acceleration bursts ~100ms apart.
    sequence = [0.30, 0.50, 0.70, 0.71, 0.40, 0.60, 0.80, 0.81]
    for i, x in enumerate(sequence):
        events.extend(det.feed(_frame(sid, i, 30.0, 0.3, x)))
    rights = [e for e in events if e.hand == "right"]
    assert len(rights) <= 1

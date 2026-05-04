"""Heuristic punch detector — synthetic pose stream, no camera needed."""

from __future__ import annotations

from uuid import uuid4

from analyze import HeuristicPunchDetector
from analyze.punch_detector_heuristic import LM_LEFT_WRIST, LM_RIGHT_WRIST
from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame


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

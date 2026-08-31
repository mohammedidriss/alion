"""ExtensionCyclePunchDetector — synthetic sequences (ADR 009).

Builds pose frames with a scripted right-wrist trajectory and checks the
detector counts a punch only on a genuine ballistic out-and-back excursion.
"""

from __future__ import annotations

from uuid import uuid4

from analyze import ExtensionCyclePunchDetector, detect_punches_extension
from contracts import PoseFrame, WorldLandmark

SID = uuid4()
FPS_DT = 1000.0 / 30.0  # 30 fps

# Landmark indices used by the detector.
_R_SHOULDER, _R_WRIST = 12, 16
_L_SHOULDER, _L_WRIST = 11, 15


def _frame(i: int, r_wrist_x: float) -> PoseFrame:
    """A frame with the right shoulder at origin and right wrist at (x,0,0).

    Left arm parked in a small fixed position so it never fires.
    """
    wl = [WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=1.0) for _ in range(33)]
    wl[_R_SHOULDER] = WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=1.0)
    wl[_R_WRIST] = WorldLandmark(x=r_wrist_x, y=0.0, z=0.0, visibility=1.0)
    wl[_L_SHOULDER] = WorldLandmark(x=-0.4, y=0.0, z=0.0, visibility=1.0)
    wl[_L_WRIST] = WorldLandmark(x=-0.45, y=0.0, z=0.0, visibility=1.0)
    # Image landmarks are required but unused on the world path; reuse coords.
    from contracts import Landmark

    lm = tuple(Landmark(x=w.x, y=w.y, z=w.z, visibility=1.0) for w in wl)
    return PoseFrame(
        session_id=SID,
        frame_index=i,
        t_ms=i * FPS_DT,
        landmarks=lm,
        world_landmarks=tuple(wl),
    )


def _run(xs: list[float], **kwargs) -> int:
    det = ExtensionCyclePunchDetector(stance="orthodox", **kwargs)
    n = 0
    for i, x in enumerate(xs):
        n += len(det.feed(_frame(i, x)))
    return n


def _chamber(n: int) -> list[float]:
    return [0.05] * n  # wrist 0.05 m from shoulder = guard


def _ballistic_punch() -> list[float]:
    # Fast extension 0.05 → 0.55 over ~4 frames (~3.5-4.5 m/s), then retract.
    return [0.18, 0.34, 0.48, 0.55, 0.44, 0.28, 0.12, 0.05]


def test_clean_punch_counts_one() -> None:
    xs = _chamber(5) + _ballistic_punch() + _chamber(5)
    assert _run(xs) == 1


def test_two_punches_count_two() -> None:
    xs = _chamber(5) + _ballistic_punch() + _chamber(6) + _ballistic_punch() + _chamber(5)
    assert _run(xs) == 2


def test_jitter_counts_zero() -> None:
    # Tiny wrist wobble near guard — small amplitude, low speed.
    xs = []
    for k in range(60):
        xs.append(0.05 + (0.01 if k % 2 else -0.01))
    assert _run(xs) == 0


def test_slow_reach_counts_zero() -> None:
    # Extend fully but slowly (20 frames): high amplitude, sub-threshold speed.
    up = [0.05 + (0.5 * k / 20) for k in range(21)]
    down = list(reversed(up))
    assert _run(up + down) == 0


def test_velocity_threshold_gates() -> None:
    xs = _chamber(5) + _ballistic_punch() + _chamber(5)
    # An absurdly high ballistic-speed bar rejects even the clean punch.
    assert _run(xs, min_peak_velocity_ms=50.0) == 0


def test_near_misses_property_empty() -> None:
    assert ExtensionCyclePunchDetector().near_misses == []


def test_detect_helper_matches_streaming() -> None:
    xs = _chamber(5) + _ballistic_punch() + _chamber(5)
    frames = [_frame(i, x) for i, x in enumerate(xs)]
    events = detect_punches_extension(frames, stance="orthodox")
    assert len(events) == 1
    assert events[0].hand == "right"
    assert events[0].detected_by == "heuristic"
    assert events[0].velocity_ms > 0

"""Wrist ↔ camera cross-check (analyze.punch_fusion)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from analyze.punch_fusion import (
    WristPunch,
    cross_check,
    hands_verdict,
    smooth_pose,
    sync_offset,
    vote,
    wrist_gaps,
)
from contracts import Hand, Landmark, PoseFrame, PunchEvent, WorldLandmark

SID = uuid4()


def ev(t: float, hand: Hand = "left", v: float = 2.0) -> PunchEvent:
    return PunchEvent(
        session_id=SID, t_ms=t, hand=hand, velocity_ms=v, detected_by="heuristic", confidence=0.5
    )


def other(hand: Hand) -> Hand:
    return "right" if hand == "left" else "left"


def test_cameras_vote_out_one_cameras_jitter() -> None:
    cams = {
        "laptop": [ev(1000), ev(5000)],  # 5000: only the laptop saw it
        "phone": [ev(1060, v=3.0)],
        "iphone": [ev(1100, v=4.0), ev(9000)],
    }
    votes = vote(cams)
    assert [(round(v.t_ms), v.cameras, v.speed_ms) for v in votes] == [
        (1060, ("iphone", "laptop", "phone"), 3.0)
    ]
    # one camera: its own punches are the vote
    assert len(vote({"laptop": [ev(1000), ev(5000)]})) == 2


def test_both_sides_confirm_and_disagreements_are_reported() -> None:
    wrist = [
        WristPunch(1000, "left", 6.0),
        WristPunch(2000, "right", 8.0),
        WristPunch(3000, "left", 5.0),
    ]
    cams = {
        "a": [ev(1050, "left"), ev(2030, "right"), ev(4000, "right")],
        "b": [ev(1040, "left"), ev(2010, "right"), ev(4020, "right")],
    }
    cc = cross_check(wrist, cams, gaps={"left": [], "right": []})
    got = [(round(p.t_ms), p.source, p.counted, p.peak_g) for p in cc.punches]
    assert got == [
        (1000, "both", True, 6.0),  # the wrist's time and impact…
        (2000, "both", True, 8.0),
        (3000, "wrist", True, 5.0),  # the cameras missed it: still counted
        (4010, "camera", False, None),  # wrists streaming and felt nothing
    ]
    assert cc.punches[0].speed_ms == 2.0 and cc.punches[0].cameras == (
        "a",
        "b",
    )  # …the cameras' speed
    assert len(cc.counted) == 3


def test_camera_only_punches_count_where_a_wrist_sensor_dropped_out() -> None:
    wrist = [WristPunch(1000, "left", 6.0)]
    cams = {"a": [ev(1000, "left"), ev(4000, "right")], "b": [ev(1010, "left"), ev(4010, "right")]}
    gaps = wrist_gaps({"left": [0, 400, 800, 1200, 5000], "right": [0, 400, 800]}, 0, 5000)
    assert gaps["right"] == [(800, 5000)] and gaps["left"] == [(1200, 5000)]
    cc = cross_check(wrist, cams, gaps=gaps)
    assert [(p.source, p.counted) for p in cc.punches] == [("both", True), ("camera", True)]


def test_without_wrist_sensors_the_cameras_vote_is_the_count() -> None:
    cams = {"a": [ev(1000), ev(3000)], "b": [ev(1020), ev(3010), ev(6000)]}
    cc = cross_check([], cams)
    assert [(p.source, p.counted) for p in cc.counted] == [("camera", True), ("camera", True)]
    assert cc.cameras[0].agreement is None


def test_without_cameras_the_wrists_are_the_count() -> None:
    cc = cross_check([WristPunch(1000, "left", 6.0), WristPunch(2000, "right", 7.0)], {})
    assert [p.source for p in cc.counted] == ["wrist", "wrist"] and cc.hands == "unclear"


def _alternating(n: int, hand_shift: bool) -> tuple[list[WristPunch], dict[str, list[PunchEvent]]]:
    """n isolated punches 1 s apart; the cameras name the other hand if hand_shift."""
    hands: list[Hand] = ["left" if i % 2 else "right" for i in range(n)]
    wrist = [WristPunch(1000.0 * (i + 1), h, 5.0) for i, h in enumerate(hands)]
    cam = [ev(1000.0 * (i + 1) + 20, other(h) if hand_shift else h) for i, h in enumerate(hands)]
    return wrist, {"a": cam, "b": cam}


def test_cameras_catch_sensors_on_the_wrong_wrists_and_correct_the_hands() -> None:
    wrist, cams = _alternating(40, hand_shift=True)
    cc = cross_check(wrist, cams, gaps={"left": [], "right": []})
    assert cc.hands == "swapped" and cc.hands_swapped
    assert all(p.source == "both" for p in cc.punches)
    # the sensor labelled "right" fired first, but the cameras saw the left hand
    assert cc.punches[0].hand == "left"
    assert {r.hands for r in cc.cameras} == {"swapped"}

    wrist, cams = _alternating(40, hand_shift=False)
    cc = cross_check(wrist, cams, gaps={"left": [], "right": []})
    assert cc.hands == "consistent" and not cc.hands_swapped
    assert cc.punches[0].hand == "right"


def test_left_right_needs_isolated_punches_to_judge() -> None:
    # a fast left-right combination: both wrists within the window → no verdict
    wrist = [WristPunch(1000.0 * i, "left", 5.0) for i in range(1, 41)]
    wrist += [WristPunch(1000.0 * i + 150, "right", 5.0) for i in range(1, 41)]
    wrist.sort(key=lambda w: w.t_ms)
    verdict, same, opposite = hands_verdict(
        [(1000.0 * i + 10, "right") for i in range(1, 41)], wrist
    )
    assert verdict == "unclear" and same == opposite == 0


def test_a_camera_out_of_sync_is_realigned_to_the_wrists() -> None:
    wrist = [WristPunch(1000.0 * i, "left", 5.0) for i in range(1, 31)]
    late = [ev(1000.0 * i + 400) for i in range(1, 31)]  # this phone's clock is 400 ms behind
    assert sync_offset([e.t_ms for e in late], [w.t_ms for w in wrist]) == pytest.approx(400.0)
    on_time = [ev(1000.0 * i + 10) for i in range(1, 31)]
    cc = cross_check(wrist, {"late": late, "laptop": on_time}, gaps={"left": [], "right": []})
    assert len([p for p in cc.punches if p.source == "both"]) == 30
    late_report = next(r for r in cc.cameras if r.device == "late")
    assert late_report.offset_ms == pytest.approx(400.0) and late_report.agreement == 1.0


def _frame(t: float, wrist_x: float) -> PoseFrame:
    lms = tuple(Landmark(x=0.5, y=0.5, z=0.0, visibility=0.9) for _ in range(33))
    wls = [WorldLandmark(x=0.0, y=0.0, z=0.0, visibility=0.9) for _ in range(33)]
    wls[15] = WorldLandmark(x=wrist_x, y=0.0, z=0.0, visibility=0.9)
    return PoseFrame(
        session_id=SID, frame_index=0, t_ms=t, landmarks=lms, world_landmarks=tuple(wls)
    )


def test_smoothing_resamples_to_30_hz_and_irons_out_jitter() -> None:
    # 60 fps with ±1 cm alternating jitter on the left wrist
    frames = [_frame(i * 1000 / 60, 0.01 if i % 2 else -0.01) for i in range(120)]
    out = smooth_pose(frames)
    assert len(out) == 60  # 2 s at 30 Hz
    assert [f.frame_index for f in out[:3]] == [0, 1, 2]
    xs = [f.world_landmarks[15].x for f in out[2:-2] if f.world_landmarks]
    assert max(abs(x) for x in xs) < 0.003

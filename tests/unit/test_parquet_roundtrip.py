"""Pose parquet writer ↔ reader symmetry. Doesn't need mediapipe/opencv."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from capture.cv.writer import read_pose_parquet, write_pose_parquet
from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame


def _frame(session_id, idx: int, t_ms: float) -> PoseFrame:  # type: ignore[no-untyped-def]
    landmarks = tuple(
        Landmark(x=0.5 + 0.001 * i, y=0.5, z=0.0, visibility=0.9) for i in range(NUM_POSE_LANDMARKS)
    )
    return PoseFrame(session_id=session_id, frame_index=idx, t_ms=t_ms, landmarks=landmarks)


def test_round_trip(tmp_path: Path) -> None:
    sid = uuid4()
    frames = [_frame(sid, i, i * 33.33) for i in range(5)]
    out = write_pose_parquet(tmp_path / "p.parquet", frames)
    back = read_pose_parquet(out)
    assert len(back) == 5
    assert back[0].session_id == sid
    assert back[2].frame_index == 2
    assert back[4].t_ms == frames[4].t_ms
    assert len(back[0].landmarks) == NUM_POSE_LANDMARKS


def test_empty_roundtrip(tmp_path: Path) -> None:
    out = write_pose_parquet(tmp_path / "empty.parquet", [])
    assert read_pose_parquet(out) == []

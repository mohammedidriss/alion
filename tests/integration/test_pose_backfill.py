"""Pose that a browser camera didn't send is recovered from its clip
(services.pose_backfill) — the page's pose model wasn't loaded at Start, or the
page went off screen, while the video kept recording."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from contracts import Landmark, PoseFrame


def _frames(take: UUID, n: int, step_ms: float = 33.3) -> list[PoseFrame]:
    lms = tuple(Landmark(x=0.5, y=0.5, z=0.0, visibility=0.9) for _ in range(33))
    return [
        PoseFrame(session_id=take, frame_index=i, t_ms=i * step_ms, landmarks=lms) for i in range(n)
    ]


@pytest.fixture
def take(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[UUID, Path]]:
    from api.services import dataset_store

    monkeypatch.setattr(dataset_store, "DATASETS_DIR", tmp_path / "datasets")
    tid = uuid4()
    folder = dataset_store.create_take_dir(uuid4(), tid, {"duration_ms": 50_000.0})
    (folder / "video").mkdir(exist_ok=True)
    for dev, offset in (("laptop1", 100.0), ("iphone1", 10.0), ("k1", 600.0)):
        (folder / "video" / f"{dev}.webm").write_bytes(b"\x1a\x45\xdf\xa3clip")
        (folder / "video" / f"{dev}.json").write_text(f'{{"start_offset_ms": {offset}}}')
    yield tid, folder


def test_cameras_missing_pose_are_found_and_recovered_from_their_clip(
    take: tuple[UUID, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import pose_backfill
    from capture.cv.writer import read_pose_parquet, write_pose_parquet

    tid, folder = take
    (folder / "pose").mkdir(exist_ok=True)
    write_pose_parquet(folder / "pose" / "iphone1.parquet", _frames(tid, 1500))  # ~50 s ✓
    write_pose_parquet(folder / "pose" / "k1.parquet", _frames(tid, 4))  # stopped at once
    # laptop1: no pose at all (its model wasn't loaded when Start came)

    gaps = {g.device_id: g for g in pose_backfill.take_gaps(folder)}
    assert sorted(gaps) == ["k1", "laptop1"]
    assert gaps["laptop1"].coverage == 0.0 and gaps["laptop1"].start_offset_ms == 100.0

    def fake_recover(capture: UUID, gap: pose_backfill.PoseGap) -> int:
        # the real one runs MediaPipe over the clip; frames land on the take's timeline
        frames = [
            f.model_copy(update={"t_ms": f.t_ms + (gap.start_offset_ms or 0)})
            for f in _frames(tid, 1490)
        ]
        write_pose_parquet(gap.pose, frames)
        return len(frames)

    monkeypatch.setattr(pose_backfill, "recover_clip", fake_recover)
    done = pose_backfill.recover_take(tid)
    assert {d: v["frames"] for d, v in done.items()} == {"k1": 1490, "laptop1": 1490}
    assert read_pose_parquet(folder / "pose" / "laptop1.parquet")[0].t_ms == 100.0
    from api.services import dataset_store

    assert dataset_store.read_take_json(folder)["pose_source"] == {
        "iphone1": "browser",
        "k1": "video",
        "laptop1": "video",
    }
    assert pose_backfill.take_gaps(folder) == []  # nothing left to recover

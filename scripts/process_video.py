"""Process an MP4 file end-to-end (no preview).

Usage:
    uv run python scripts/process_video.py <video.mp4> --fighter <fighter_id>
"""

from __future__ import annotations

import argparse
from pathlib import Path
from uuid import UUID

from analyze import HeuristicPunchDetector
from capture.cv import CapturePipeline, FileSource
from common import setup_logging
from store import (
    DetectionSourceEnum,
    HandEnum,
    PunchEventRepo,
    PunchEventRow,
    SessionCreate,
    SessionRepo,
    SessionSourceEnum,
    SessionStatus,
    create_db_and_tables,
    get_session,
)


def main() -> None:
    setup_logging("INFO")
    p = argparse.ArgumentParser()
    p.add_argument("video", type=Path)
    p.add_argument("--fighter", required=True)
    args = p.parse_args()

    if not args.video.exists():
        raise SystemExit(f"video not found: {args.video}")

    create_db_and_tables()
    fighter_id = UUID(args.fighter)

    db_gen = get_session()
    db = next(db_gen)
    try:
        sess = SessionRepo(db).create(
            SessionCreate(fighter_id=fighter_id, source=SessionSourceEnum.UPLOADED_VIDEO)
        )
        session_id = sess.id
        SessionRepo(db).attach_artifacts(session_id, video_path=str(args.video))
        SessionRepo(db).update_status(session_id, SessionStatus.PROCESSING)
        print(f"session: {session_id}")

        detector = HeuristicPunchDetector()
        events_buffer: list[PunchEventRow] = []

        def on_frame(pose) -> None:  # type: ignore[no-untyped-def]
            for ev in detector.feed(pose):
                events_buffer.append(
                    PunchEventRow(
                        session_id=ev.session_id,
                        t_ms=ev.t_ms,
                        hand=HandEnum(ev.hand),
                        velocity_ms=ev.velocity_ms,
                        detected_by=DetectionSourceEnum(ev.detected_by),
                        confidence=ev.confidence,
                    )
                )

        parquet_path = Path("data/processed") / f"{session_id}.pose.parquet"
        result = CapturePipeline(
            session_id=session_id,
            source=FileSource(args.video),
            parquet_path=parquet_path,
            on_frame=on_frame,
        ).run()

        PunchEventRepo(db).add_many(events_buffer)
        SessionRepo(db).attach_artifacts(
            session_id,
            pose_parquet_path=str(result.parquet_path),
            frame_count=result.frame_count,
            duration_ms=result.duration_ms,
        )
        SessionRepo(db).update_status(session_id, SessionStatus.COMPLETED, end=True)
        print(
            f"done: {result.frame_count} frames, "
            f"{result.duration_ms / 1000:.1f}s, {len(events_buffer)} punches"
        )
    finally:
        db_gen.close()


if __name__ == "__main__":
    main()

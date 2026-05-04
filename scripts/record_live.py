"""Record a live webcam session with on-screen preview.

Usage:
    uv run python scripts/record_live.py --fighter <fighter_id> [--show] [--max-frames 900]

Shows a cv2 window with the pose skeleton overlay and a flash on each detected
punch. Press 'q' to stop. Persists pose parquet + punch events to the DB.
"""

from __future__ import annotations

import argparse
from uuid import UUID

from analyze import HeuristicPunchDetector
from capture.cv import CapturePipeline, WebcamSource
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
    p.add_argument("--fighter", required=True, help="fighter UUID")
    p.add_argument("--show", action="store_true", help="show cv2 preview window")
    p.add_argument("--max-frames", type=int, default=None)
    args = p.parse_args()

    create_db_and_tables()
    fighter_id = UUID(args.fighter)

    db_gen = get_session()
    db = next(db_gen)
    try:
        sess = SessionRepo(db).create(
            SessionCreate(fighter_id=fighter_id, source=SessionSourceEnum.LIVE_WEBCAM)
        )
        session_id = sess.id
        print(f"session: {session_id}")

        SessionRepo(db).update_status(session_id, SessionStatus.CAPTURING)

        detector = HeuristicPunchDetector()
        events_buffer: list[PunchEventRow] = []
        last_event_t = {"left": -9999.0, "right": -9999.0}

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
                last_event_t[ev.hand] = ev.t_ms
                print(
                    f"  punch t={ev.t_ms:7.0f}ms hand={ev.hand:5s} "
                    f"v={ev.velocity_ms:.2f}m/s conf={ev.confidence:.2f}"
                )

        on_raw_frame = None
        if args.show:
            import cv2
            import mediapipe as mp  # type: ignore[import-not-found]

            mp_drawing = mp.solutions.drawing_utils
            mp_pose = mp.solutions.pose
            cv2.namedWindow("Alion — live", cv2.WINDOW_NORMAL)

            def on_raw_frame(raw, pose) -> None:  # type: ignore[no-untyped-def]
                if pose is not None:
                    # Draw skeleton from the contracts.PoseFrame coordinates.
                    h, w = raw.shape[:2]
                    for lm in pose.landmarks:
                        if lm.visibility >= 0.5:
                            cv2.circle(raw, (int(lm.x * w), int(lm.y * h)), 3, (0, 255, 0), -1)
                # Flash on recent events.
                for hand, t in last_event_t.items():
                    if pose is not None and pose.t_ms - t < 200:
                        color = (0, 200, 255) if hand == "left" else (255, 200, 0)
                        cv2.putText(
                            raw,
                            hand.upper(),
                            (20 if hand == "left" else 250, 60),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1.5,
                            color,
                            3,
                        )
                cv2.imshow("Alion — live", raw)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    raise KeyboardInterrupt()

            _ = mp_drawing, mp_pose  # silence unused imports

        from pathlib import Path

        parquet_path = Path("data/processed") / f"{session_id}.pose.parquet"
        pipeline = CapturePipeline(
            session_id=session_id,
            source=WebcamSource(0),
            parquet_path=parquet_path,
            on_frame=on_frame,
            on_raw_frame=on_raw_frame,
            max_frames=args.max_frames,
        )

        try:
            result = pipeline.run()
        except KeyboardInterrupt:
            print("\nstopped by user")
            result = None

        if args.show:
            import cv2

            cv2.destroyAllWindows()

        PunchEventRepo(db).add_many(events_buffer)
        if result is not None:
            SessionRepo(db).attach_artifacts(
                session_id,
                pose_parquet_path=str(result.parquet_path),
                frame_count=result.frame_count,
                duration_ms=result.duration_ms,
            )
        SessionRepo(db).update_status(session_id, SessionStatus.COMPLETED, end=True)
        print(f"done: {len(events_buffer)} punches detected")
    finally:
        db_gen.close()


if __name__ == "__main__":
    main()

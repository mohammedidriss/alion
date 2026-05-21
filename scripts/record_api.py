"""Record a live webcam session and sync results to a remote Alion API.

Usage:
    uv run python scripts/record_api.py \\
        --fighter <fighter_id> \\
        --api-url https://your-api.railway.app \\
        --token <jwt_token> \\
        [--show] [--max-frames 900]

The script:
  1. Creates a session via the remote API.
  2. Runs the CV capture pipeline locally (requires opencv + mediapipe on this machine).
  3. Pushes all punch events + metadata back to the remote API.

Get your JWT token by logging in:
    curl -X POST <api_url>/auth/login -H "Content-Type: application/json" \\
         -d '{"email":"you@example.com","password":"yourpassword"}'
"""

from __future__ import annotations

import argparse
import os
import sys

import requests


def get_token_from_login(api_url: str, email: str, password: str) -> str:
    r = requests.post(f"{api_url}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["access_token"]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fighter", required=True, help="fighter UUID")
    p.add_argument("--api-url", default=os.environ.get("ALION_API_URL", ""), help="Base API URL")
    p.add_argument("--token", default=os.environ.get("ALION_TOKEN", ""), help="JWT bearer token")
    p.add_argument("--email", default=os.environ.get("ALION_EMAIL", ""))
    p.add_argument("--password", default=os.environ.get("ALION_PASSWORD", ""))
    p.add_argument("--show", action="store_true", help="show cv2 preview window")
    p.add_argument("--max-frames", type=int, default=None)
    p.add_argument("--camera", type=int, default=0)
    args = p.parse_args()

    api_url = args.api_url.rstrip("/")
    if not api_url:
        sys.exit("--api-url or ALION_API_URL env var required")

    token = args.token
    if not token:
        if args.email and args.password:
            print("Logging in…")
            token = get_token_from_login(api_url, args.email, args.password)
        else:
            sys.exit("Provide --token or --email + --password (or set ALION_TOKEN env var)")

    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create session on remote API
    print(f"Creating session for fighter {args.fighter}…")
    r = requests.post(
        f"{api_url}/sessions",
        json={"fighter_id": args.fighter, "source": "live_webcam"},
        headers=headers,
    )
    if r.status_code != 201:
        sys.exit(f"Failed to create session: {r.status_code} {r.text}")
    session_id = r.json()["id"]
    print(f"Session: {session_id}")

    # 2. Run local capture
    from analyze import HeuristicPunchDetector
    from capture.cv import CapturePipeline, WebcamSource

    detector = HeuristicPunchDetector()
    events_buffer: list[dict] = []
    last_event_t: dict[str, float] = {"left": -9999.0, "right": -9999.0}

    from uuid import UUID

    sid = UUID(session_id)

    def on_frame(pose) -> None:  # type: ignore[no-untyped-def]
        for ev in detector.feed(pose):
            events_buffer.append(
                {
                    "t_ms": ev.t_ms,
                    "hand": ev.hand,
                    "velocity_ms": ev.velocity_ms,
                    "confidence": ev.confidence,
                    "detected_by": ev.detected_by,
                }
            )
            last_event_t[ev.hand] = ev.t_ms
            print(
                f"  punch t={ev.t_ms:7.0f}ms hand={ev.hand:5s} "
                f"v={ev.velocity_ms:.2f}m/s conf={ev.confidence:.2f}"
            )

    on_raw_frame = None
    if args.show:
        import cv2

        cv2.namedWindow("Alion — live", cv2.WINDOW_NORMAL)

        def on_raw_frame(raw, pose) -> None:  # type: ignore[no-untyped-def]
            if pose is not None:
                h, w = raw.shape[:2]
                for lm in pose.landmarks:
                    if lm.visibility >= 0.5:
                        cv2.circle(raw, (int(lm.x * w), int(lm.y * h)), 3, (0, 255, 0), -1)
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

    from pathlib import Path

    parquet_path = Path("data/processed") / f"{session_id}.pose.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)

    pipeline = CapturePipeline(
        session_id=sid,
        source=WebcamSource(args.camera),
        parquet_path=parquet_path,
        on_frame=on_frame,
        on_raw_frame=on_raw_frame,
        max_frames=args.max_frames,
    )

    print("Recording… press q (with --show) or Ctrl-C to stop.")
    try:
        result = pipeline.run()
    except KeyboardInterrupt:
        print("\nStopped by user.")
        result = None

    if args.show:
        import cv2

        cv2.destroyAllWindows()

    # 3. Push events + metadata to remote API
    print(f"Uploading {len(events_buffer)} events to {api_url}…")
    payload: dict = {"events": events_buffer}
    if result is not None:
        payload["frame_count"] = result.frame_count
        payload["duration_ms"] = result.duration_ms

    r = requests.post(
        f"{api_url}/sessions/{session_id}/events/bulk",
        json=payload,
        headers=headers,
    )
    if r.status_code != 200:
        print(f"WARNING: upload failed: {r.status_code} {r.text}")
    else:
        print(f"Done: {r.json()['inserted']} punches saved.")


if __name__ == "__main__":
    main()

"""Probe the local webcam and trigger the macOS permission dialog if needed.

Usage:
    uv run python scripts/check_camera.py

What it does:
1. Tries to open the default webcam (cv2.VideoCapture(0)).
2. Reads a few frames — this is what actually triggers macOS TCC.
3. Prints clear next-step guidance based on the outcome.

This is the prerequisite for using the dashboard's "Start live capture"
button. The first time it runs, macOS should pop a "Terminal would like
to access the camera" dialog. Click Allow, then re-run to confirm.
"""

from __future__ import annotations

import os
import platform
import sys


def _hint_macos_permission() -> str:
    return (
        "macOS most likely denied camera access to this terminal.\n"
        "  1. Open System Settings → Privacy & Security → Camera.\n"
        "  2. If your terminal app is listed, toggle it on.\n"
        "  3. If it isn't listed, run this script from a *new*\n"
        "     Terminal.app window (Spotlight → 'Terminal') so the\n"
        "     permission dialog has a chance to pop. Click Allow.\n"
        "  4. Quit and reopen the terminal so the grant takes effect.\n"
        "  5. Make sure no other app is using the camera (Zoom, FaceTime,\n"
        "     Photo Booth, browser tabs that did getUserMedia)."
    )


def main() -> int:
    try:
        import cv2
    except ImportError:
        print("✗ opencv-python is not installed.")
        print("  Run: uv sync --extra dev --extra capture")
        return 2

    import cv2

    is_macos = platform.system() == "Darwin"
    print(f"platform: {platform.system()} {platform.release()}")
    print(f"opencv:   {cv2.__version__}")
    print()

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        cap.release()
        print("✗ cv2.VideoCapture(0) returned not-opened.")
        if is_macos:
            print()
            print(_hint_macos_permission())
        else:
            print("  No camera found at index 0. Try a different index or check device.")
        return 1

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"opened ✓ ({width}x{height})")

    # Reading frames is what actually requests TCC permission on macOS.
    ok_frames = 0
    last_shape: tuple[int, ...] | None = None
    for i in range(10):
        ok, frame = cap.read()
        if ok and frame is not None:
            ok_frames += 1
            last_shape = frame.shape
        elif ok_frames == 0 and i >= 2:
            # Failing fast on the very first reads typically means TCC denied.
            break
    cap.release()

    if ok_frames == 0:
        print("✗ Could not read any frames from the camera.")
        if is_macos:
            print()
            print(_hint_macos_permission())
        return 1

    print(f"read    ✓ {ok_frames}/10 frames; last frame shape={last_shape}")
    print()
    print("Camera works. You're ready to:")
    print("  • run `uv run uvicorn api.main:app --reload`")
    print("  • create a live_webcam session in the dashboard")
    print("  • click 'Start live capture'")
    return 0


if __name__ == "__main__":
    # Tame OpenCV's chatter on macOS so the script's own output stands out.
    os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")
    sys.exit(main())

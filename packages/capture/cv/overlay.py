"""Draw a MediaPipe-style pose skeleton onto a BGR frame.

Used by the API preview endpoint so the dashboard can show a live overlay.
The drawing is intentionally minimal — circles for joints, lines for limbs.
Heavier visual styles can come in Phase 6 when the dashboard polish lands.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from contracts import PoseFrame

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    Frame = NDArray[np.uint8]
else:
    Frame = Any


# Subset of MediaPipe's POSE_CONNECTIONS — enough for a recognizable skeleton.
POSE_CONNECTIONS = (
    (11, 12),  # shoulders
    (11, 13),
    (13, 15),  # left arm
    (12, 14),
    (14, 16),  # right arm
    (11, 23),
    (12, 24),  # shoulders → hips
    (23, 24),  # hips
    (23, 25),
    (25, 27),  # left leg
    (24, 26),
    (26, 28),  # right leg
    (15, 17),
    (15, 19),
    (15, 21),  # left hand
    (16, 18),
    (16, 20),
    (16, 22),  # right hand
    (0, 1),
    (0, 4),  # face / nose
)

_LANDMARK_COLOR = (0, 255, 0)  # green
_CONNECTION_COLOR = (0, 220, 220)  # cyan
_VISIBILITY_THRESHOLD = 0.5


def draw_pose(frame: Frame, pose: PoseFrame | None) -> Frame:
    """Mutate `frame` in-place with the skeleton overlay. Returns the same frame."""
    import cv2

    if pose is None:
        return frame
    h, w = frame.shape[:2]
    pts: dict[int, tuple[int, int]] = {}
    for i, lm in enumerate(pose.landmarks):
        if lm.visibility < _VISIBILITY_THRESHOLD:
            continue
        x, y = int(lm.x * w), int(lm.y * h)
        pts[i] = (x, y)
        cv2.circle(frame, (x, y), 3, _LANDMARK_COLOR, -1, lineType=cv2.LINE_AA)
    for a, b in POSE_CONNECTIONS:
        if a in pts and b in pts:
            cv2.line(frame, pts[a], pts[b], _CONNECTION_COLOR, 2, lineType=cv2.LINE_AA)
    return frame

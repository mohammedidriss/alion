"""MediaPipe Pose wrapper. Lazy-imports mediapipe so the module is importable
on machines without the capture extras installed.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    Frame = NDArray[np.uint8]
else:
    Frame = Any


class PoseEstimator:
    """Wraps MediaPipe Pose. Produces a `PoseFrame` per RGB frame."""

    def __init__(
        self,
        session_id: UUID,
        fps: float,
        *,
        model_complexity: int = 1,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self.session_id = session_id
        self.fps = fps
        self._frame_idx = 0
        self._mp_pose: Any = None
        self._opts = {
            "model_complexity": model_complexity,
            "min_detection_confidence": min_detection_confidence,
            "min_tracking_confidence": min_tracking_confidence,
            "enable_segmentation": False,
        }

    @contextmanager
    def open(self) -> Iterator[PoseEstimator]:
        import mediapipe as mp

        self._mp_pose = mp.solutions.pose.Pose(**self._opts)
        try:
            yield self
        finally:
            self._mp_pose.close()
            self._mp_pose = None

    def process(self, bgr_frame: Frame) -> PoseFrame | None:
        """Run pose on one BGR frame. Returns None if no person detected."""
        import cv2

        if self._mp_pose is None:
            raise RuntimeError("PoseEstimator not opened — use `with estimator.open():`")
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._mp_pose.process(rgb)
        idx = self._frame_idx
        self._frame_idx += 1
        if result.pose_landmarks is None:
            return None
        landmarks = tuple(
            Landmark(x=lm.x, y=lm.y, z=lm.z, visibility=max(0.0, min(1.0, lm.visibility)))
            for lm in result.pose_landmarks.landmark
        )
        if len(landmarks) != NUM_POSE_LANDMARKS:
            return None
        return PoseFrame(
            session_id=self.session_id,
            frame_index=idx,
            t_ms=(idx / self.fps) * 1000.0,
            landmarks=landmarks,
        )

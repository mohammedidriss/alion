"""MediaPipe Pose wrapper using the Tasks API (`mediapipe.tasks.vision`).

The legacy `mediapipe.solutions.pose` module is gone in recent builds on
Apple Silicon. The Tasks API needs a model asset downloaded once; we cache
it under `models/mediapipe/` and gitignore it.

Lazy-imports mediapipe so the module is importable on machines without the
capture extras installed.
"""

from __future__ import annotations

import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from contracts import NUM_POSE_LANDMARKS, Landmark, PoseFrame, WorldLandmark

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray

    Frame = NDArray[np.uint8]
else:
    Frame = Any


_MODEL_DIR = Path("models/mediapipe")
# "lite" for live capture; "full" matches what the browser cameras run, used when
# pose is recovered from a recorded clip.
PoseModel = Literal["lite", "full"]


def _model_url(model: PoseModel) -> str:
    return (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        f"pose_landmarker_{model}/float16/latest/pose_landmarker_{model}.task"
    )


def ensure_pose_model(model: PoseModel = "lite") -> Path:
    """Download the pose landmarker model on first use; return its path."""
    path = _MODEL_DIR / f"pose_landmarker_{model}.task"
    if path.exists():
        return path
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".task.partial")
    urllib.request.urlretrieve(_model_url(model), tmp)
    tmp.rename(path)
    return path


class PoseEstimator:
    """Wraps MediaPipe Pose (Tasks API). Produces a `PoseFrame` per BGR frame."""

    def __init__(
        self,
        session_id: UUID,
        fps: float,
        *,
        min_detection_confidence: float = 0.5,
        min_presence_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
        model: PoseModel = "lite",
    ) -> None:
        self.session_id = session_id
        self.fps = fps
        self.model: PoseModel = model
        self._frame_idx = 0
        self._landmarker: Any = None
        self._opts = {
            "min_detection": min_detection_confidence,
            "min_presence": min_presence_confidence,
            "min_tracking": min_tracking_confidence,
        }

    @contextmanager
    def open(self) -> Iterator[PoseEstimator]:
        import mediapipe as mp
        from mediapipe.tasks import python as mp_python
        from mediapipe.tasks.python import vision as mp_vision

        model_path = ensure_pose_model(self.model)
        options = mp_vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(model_path)),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=self._opts["min_detection"],
            min_pose_presence_confidence=self._opts["min_presence"],
            min_tracking_confidence=self._opts["min_tracking"],
        )
        self._landmarker = mp_vision.PoseLandmarker.create_from_options(options)
        # Stash refs so process() can build mp.Image without re-importing.
        self._mp = mp
        try:
            yield self
        finally:
            self._landmarker.close()
            self._landmarker = None

    def process(self, bgr_frame: Frame, t_ms: float | None = None) -> PoseFrame | None:
        """Run pose on one BGR frame. Returns None if no person detected.

        `t_ms` is the frame's own time (a recorded clip's frames don't come at a
        fixed rate); without it, time is the frame index over `fps`."""
        import cv2

        if self._landmarker is None:
            raise RuntimeError("PoseEstimator not opened — use `with estimator.open():`")
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        idx = self._frame_idx
        self._frame_idx += 1
        t = t_ms if t_ms is not None else (idx / self.fps) * 1000.0
        # MediaPipe needs strictly increasing timestamps.
        t_ms_int = max(int(t), getattr(self, "_last_ts", -1) + 1)
        self._last_ts = t_ms_int
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect_for_video(mp_image, t_ms_int)
        if not result.pose_landmarks:
            return None
        first = result.pose_landmarks[0]
        if len(first) != NUM_POSE_LANDMARKS:
            return None
        landmarks = tuple(
            Landmark(
                x=lm.x,
                y=lm.y,
                z=lm.z,
                visibility=max(0.0, min(1.0, getattr(lm, "visibility", 1.0) or 0.0)),
            )
            for lm in first
        )
        # World landmarks: hip-centered metric 3D. Optional — older MediaPipe
        # builds may not return them; we silently fall back to None.
        world_lms: tuple[WorldLandmark, ...] | None = None
        wl = getattr(result, "pose_world_landmarks", None)
        if wl and len(wl) > 0 and len(wl[0]) == NUM_POSE_LANDMARKS:
            world_lms = tuple(
                WorldLandmark(
                    x=lm.x,
                    y=lm.y,
                    z=lm.z,
                    visibility=max(0.0, min(1.0, getattr(lm, "visibility", 1.0) or 0.0)),
                )
                for lm in wl[0]
            )
        return PoseFrame(
            session_id=self.session_id,
            frame_index=idx,
            t_ms=t,
            landmarks=landmarks,
            world_landmarks=world_lms,
        )

"""CV capture sub-module.

Provides a `FrameSource` abstraction (webcam or file), a MediaPipe Pose wrapper
that turns frames into `PoseFrame` events, and a parquet writer for
keypoint sequences. Heavy CV deps (mediapipe, cv2) are imported lazily so the
core API runs without them when capture is not used.
"""

from capture.cv.pipeline import CapturePipeline, CapturePipelineResult
from capture.cv.sources import FileSource, FrameSource, WebcamSource
from capture.cv.writer import PoseParquetWriter, read_pose_parquet

__all__ = [
    "CapturePipeline",
    "CapturePipelineResult",
    "FileSource",
    "FrameSource",
    "PoseParquetWriter",
    "WebcamSource",
    "read_pose_parquet",
]

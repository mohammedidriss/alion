"""DeepSORT multi-person tracker for identity persistence across frames.

Wraps `deep-sort-realtime` to maintain stable fighter IDs through
occlusion, camera jitter, and overlapping bounding boxes. Each tracked
identity gets a unique integer `track_id` that persists across frames.

Usage with YOLOPoseEstimator:

    tracker = DeepSORTTracker()
    with yolo.open() as est:
        for frame in source:
            detections = est.process_multi(frame)
            tracked = tracker.update(detections, frame)
            for track_id, pose_frame in tracked:
                # track_id is stable across frames
                ...

Requires: `pip install deep-sort-realtime` (or `uv sync --extra yolo`).
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


class DeepSORTTracker:
    """Maintains persistent identity tracking for multi-person sessions.

    Parameters
    ----------
    max_age : int
        Maximum frames a track survives without a detection update before
        being deleted. Higher values tolerate longer occlusions.
    n_init : int
        Minimum consecutive detections before a track is confirmed.
        Prevents phantom tracks from single-frame false positives.
    max_iou_distance : float
        Maximum IoU distance for bounding-box association. Lower values
        are stricter (require more overlap).
    """

    def __init__(
        self,
        *,
        max_age: int = 30,
        n_init: int = 3,
        max_iou_distance: float = 0.7,
    ) -> None:
        self._max_age = max_age
        self._n_init = n_init
        self._max_iou_distance = max_iou_distance
        self._tracker: Any = None
        self._initialized = False

    def _ensure_tracker(self) -> Any:
        """Lazy-init the DeepSORT tracker on first use."""
        if self._tracker is None:
            from deep_sort_realtime.deepsort_tracker import DeepSort

            self._tracker = DeepSort(
                max_age=self._max_age,
                n_init=self._n_init,
                max_iou_distance=self._max_iou_distance,
            )
        return self._tracker

    def update(
        self,
        detections: list[tuple[PoseFrame, Any]],
        bgr_frame: Frame,
    ) -> list[tuple[int, PoseFrame]]:
        """Feed detections from YOLOPoseEstimator.process_multi() and return
        tracked (track_id, PoseFrame) pairs.

        Parameters
        ----------
        detections : list of (PoseFrame, bbox_xyxy)
            Output from `YOLOPoseEstimator.process_multi()`.
        bgr_frame : ndarray
            The BGR frame — DeepSORT uses it for Re-ID feature extraction.

        Returns
        -------
        list of (track_id, PoseFrame)
            Each PoseFrame is associated with a persistent integer track_id.
        """
        import numpy as np

        tracker = self._ensure_tracker()

        if not detections:
            # Still update the tracker so tracks age out.
            tracker.update_tracks([], frame=bgr_frame)
            return []

        # DeepSORT expects detections as [[x1, y1, w, h, confidence], ...]
        raw_detections: list[tuple[list[float], float, str]] = []
        pose_map: dict[int, PoseFrame] = {}

        for i, (pose_frame, bbox) in enumerate(detections):
            if bbox is None:
                continue
            x1, y1, x2, y2 = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            w, h = x2 - x1, y2 - y1
            # Confidence from average landmark visibility.
            avg_vis = float(
                np.mean([lm.visibility for lm in pose_frame.landmarks if lm.visibility > 0])
            )
            raw_detections.append(([x1, y1, w, h], avg_vis, "person"))
            pose_map[i] = pose_frame

        tracks = tracker.update_tracks(raw_detections, frame=bgr_frame)

        results: list[tuple[int, PoseFrame]] = []
        for track in tracks:
            if not track.is_confirmed():
                continue
            track_id = track.track_id
            det_idx = track.det_index
            if det_idx is not None and det_idx in pose_map:
                results.append((int(track_id), pose_map[det_idx]))

        return results

    def reset(self) -> None:
        """Reset tracker state (e.g. between sessions)."""
        self._tracker = None

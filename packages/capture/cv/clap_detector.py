"""Clap-Sync detector for cross-stream sensor alignment."""

from __future__ import annotations

from contracts import PoseFrame


class ClapDetector:
    """Detects a physical 'clap' gesture (wrists meeting rapidly) to synchronize IMU and CV streams.

    This records the exact `t_ms` of the visual clap, which the Fusion Engine
    will later align against the IMU's accelerometer spike.
    """

    def __init__(self) -> None:
        self.last_distance: float | None = None
        self.clap_t_ms: float | None = None

    def feed(self, pose: PoseFrame) -> bool:
        """Process a frame and return True if a clap was detected in this frame."""
        if pose.landmarks is None:
            return False

        try:
            l_wr = pose.landmarks[15]
            r_wr = pose.landmarks[16]
        except IndexError:
            return False

        # Calculate Euclidean-like distance in normalized 2D space
        dist = ((l_wr.x - r_wr.x) ** 2 + (l_wr.y - r_wr.y) ** 2) ** 0.5

        is_clap = False
        if self.last_distance is not None:
            # A clap: wrists were significantly apart and are now touching
            if self.last_distance > 0.15 and dist < 0.05:
                is_clap = True
                self.clap_t_ms = pose.t_ms

        self.last_distance = dist
        return is_clap

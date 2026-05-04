"""Analyze — per-stream analytics. Depends only on `contracts` and `common`."""

from analyze.punch_detector_heuristic import HeuristicPunchDetector, detect_punches

__all__ = ["HeuristicPunchDetector", "detect_punches"]

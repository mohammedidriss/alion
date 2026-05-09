"""Analyze — per-stream analytics. Depends only on `contracts` and `common`."""

from analyze.hrv_metrics import RollingHRMetrics, mean_hr_bpm, rmssd_ms, sdnn_ms
from analyze.load import TrimpResult, compute_trimp, estimate_hr_max
from analyze.performance import PerformanceScore, compute_score, compute_swc
from analyze.punch_detector_heuristic import HeuristicPunchDetector, detect_punches
from analyze.punch_type_heuristic import PunchType, classify_punch_type
from analyze.readiness import (
    MIN_HISTORY,
    Readiness,
    ReadinessMode,
    compute_readiness,
)
from analyze.reconcile import ConsensusEvent, ConsensusKind, reconcile_events
from analyze.second_pass import (
    SecondPassDetector,
    StricterHeuristicSecondPass,
    default_second_pass,
)
from analyze.velocity_refiner import refine_peak_velocity

__all__ = [
    "MIN_HISTORY",
    "ConsensusEvent",
    "ConsensusKind",
    "HeuristicPunchDetector",
    "PerformanceScore",
    "PunchType",
    "Readiness",
    "ReadinessMode",
    "RollingHRMetrics",
    "SecondPassDetector",
    "StricterHeuristicSecondPass",
    "TrimpResult",
    "classify_punch_type",
    "compute_readiness",
    "compute_score",
    "compute_swc",
    "compute_trimp",
    "default_second_pass",
    "detect_punches",
    "estimate_hr_max",
    "mean_hr_bpm",
    "reconcile_events",
    "refine_peak_velocity",
    "rmssd_ms",
    "sdnn_ms",
]

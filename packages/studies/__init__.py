"""studies — evaluation harness for the dissertation.

Self-contained: depends only on `contracts` and `common`. Never imports from
sibling feature modules.

The point of this package is to produce defensible metrics — precision, recall,
F1, and a punch-type confusion matrix — by comparing detector output against
manually-labeled ground truth videos. Without this, any "96% accuracy" claim
in the dissertation is unsubstantiated.
"""

from studies.evaluation import (
    DetectedPunch,
    GroundTruthPunch,
    MatchResult,
    confusion_matrix,
    match_events,
    render_report,
)

__all__ = [
    "DetectedPunch",
    "GroundTruthPunch",
    "MatchResult",
    "confusion_matrix",
    "match_events",
    "render_report",
]

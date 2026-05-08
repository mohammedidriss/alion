"""Detector-vs-truth evaluation: precision, recall, F1, confusion matrix.

The matching strategy is greedy with a configurable tolerance window:

    For each labeled punch in chronological order:
      find the earliest UNMATCHED detection that is
        - within +/- tolerance_ms of the truth t_ms
        - on the same hand
      mark them as a true-positive pair.

    Truth punches with no match → false negatives (missed).
    Detections with no match    → false positives (hallucinated).

This is intentionally simple and conservative. A bipartite-matching variant
(Hungarian) would be marginally fairer in dense bursts, but greedy +/- 200 ms
is the standard approach in the punch-detection literature and is easier to
explain in a dissertation defence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Hand = Literal["left", "right"]


@dataclass(frozen=True)
class GroundTruthPunch:
    """One manually-labeled punch from a reference video."""

    t_ms: float
    hand: Hand
    punch_type: str | None = None  # "jab" | "cross" | "hook" | "uppercut" | None


@dataclass(frozen=True)
class DetectedPunch:
    """One punch emitted by the detector under evaluation."""

    t_ms: float
    hand: Hand
    punch_type: str | None
    confidence: float = 1.0


@dataclass(frozen=True)
class MatchedPair:
    truth: GroundTruthPunch
    detected: DetectedPunch
    abs_offset_ms: float


@dataclass(frozen=True)
class MatchResult:
    true_positives: int
    false_positives: int
    false_negatives: int
    pairs: tuple[MatchedPair, ...]
    unmatched_truth: tuple[GroundTruthPunch, ...]
    unmatched_detected: tuple[DetectedPunch, ...]

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return (2 * p * r / (p + r)) if (p + r) > 0 else 0.0

    @property
    def mean_temporal_offset_ms(self) -> float:
        return sum(p.abs_offset_ms for p in self.pairs) / len(self.pairs) if self.pairs else 0.0


def match_events(
    truth: list[GroundTruthPunch],
    detected: list[DetectedPunch],
    tolerance_ms: float = 200.0,
) -> MatchResult:
    """Greedy time-window match. Truth and detected don't need to be sorted."""
    truth_sorted = sorted(truth, key=lambda p: p.t_ms)
    det_sorted = sorted(detected, key=lambda p: p.t_ms)
    used_det: set[int] = set()
    pairs: list[MatchedPair] = []
    unmatched_truth: list[GroundTruthPunch] = []

    for t in truth_sorted:
        best_idx: int | None = None
        best_offset = float("inf")
        for i, d in enumerate(det_sorted):
            if i in used_det or d.hand != t.hand:
                continue
            offset = abs(d.t_ms - t.t_ms)
            if offset > tolerance_ms:
                continue
            if offset < best_offset:
                best_offset = offset
                best_idx = i
        if best_idx is None:
            unmatched_truth.append(t)
        else:
            used_det.add(best_idx)
            pairs.append(
                MatchedPair(
                    truth=t,
                    detected=det_sorted[best_idx],
                    abs_offset_ms=best_offset,
                )
            )

    unmatched_detected = tuple(d for i, d in enumerate(det_sorted) if i not in used_det)
    return MatchResult(
        true_positives=len(pairs),
        false_positives=len(unmatched_detected),
        false_negatives=len(unmatched_truth),
        pairs=tuple(pairs),
        unmatched_truth=tuple(unmatched_truth),
        unmatched_detected=unmatched_detected,
    )


def confusion_matrix(
    pairs: tuple[MatchedPair, ...] | list[MatchedPair],
    classes: list[str],
) -> dict[str, dict[str, int]]:
    """Per-class confusion: rows = truth label, cols = predicted label.

    Includes a sentinel "unlabeled" column for matched pairs where one side
    has no punch_type. Pairs where BOTH sides are None are ignored (no signal).
    """
    cls = [*classes, "unlabeled"]
    out: dict[str, dict[str, int]] = {r: {c: 0 for c in cls} for r in cls}
    for p in pairs:
        t = p.truth.punch_type if p.truth.punch_type in classes else "unlabeled"
        d = p.detected.punch_type if p.detected.punch_type in classes else "unlabeled"
        if t == "unlabeled" and d == "unlabeled":
            continue
        out[t][d] += 1
    return out


def per_class_metrics(
    cm: dict[str, dict[str, int]],
    classes: list[str],
) -> dict[str, dict[str, float]]:
    """Precision/recall/F1 per class from the confusion matrix."""
    out: dict[str, dict[str, float]] = {}
    for c in classes:
        tp = cm[c][c]
        fp = sum(cm[r][c] for r in cm if r != c)
        fn = sum(cm[c][col] for col in cm[c] if col != c)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        out[c] = {"precision": prec, "recall": rec, "f1": f1, "support": tp + fn}
    return out


def render_report(
    result: MatchResult,
    cm: dict[str, dict[str, int]] | None = None,
    classes: list[str] | None = None,
    *,
    tolerance_ms: float = 200.0,
) -> str:
    """Markdown evaluation report. Suitable for paste into a thesis appendix."""
    lines: list[str] = []
    lines.append("# Detector evaluation report")
    lines.append("")
    lines.append(f"- Tolerance window: ±{tolerance_ms:.0f} ms")
    lines.append(f"- True positives:  **{result.true_positives}**")
    lines.append(f"- False positives: **{result.false_positives}**")
    lines.append(f"- False negatives: **{result.false_negatives}**")
    lines.append("")
    lines.append("## Detection metrics")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append(f"| Precision | {result.precision:.3f} |")
    lines.append(f"| Recall    | {result.recall:.3f} |")
    lines.append(f"| F1        | {result.f1:.3f} |")
    lines.append(f"| Mean abs temporal offset | {result.mean_temporal_offset_ms:.1f} ms |")
    lines.append("")
    if cm is not None and classes is not None:
        lines.append("## Punch-type confusion matrix")
        lines.append("")
        cls = [*classes, "unlabeled"]
        header = "| truth \\ pred | " + " | ".join(cls) + " |"
        sep = "|---" * (len(cls) + 1) + "|"
        lines.append(header)
        lines.append(sep)
        for r in cls:
            row_vals = " | ".join(str(cm[r][c]) for c in cls)
            lines.append(f"| **{r}** | {row_vals} |")
        lines.append("")
        pcm = per_class_metrics(cm, classes)
        lines.append("## Per-class metrics")
        lines.append("")
        lines.append("| class | precision | recall | F1 | support |")
        lines.append("|---|---|---|---|---|")
        for c in classes:
            m = pcm[c]
            lines.append(
                f"| {c} | {m['precision']:.3f} | {m['recall']:.3f} | "
                f"{m['f1']:.3f} | {int(m['support'])} |"
            )
    return "\n".join(lines)


def load_labels(path: Path) -> list[GroundTruthPunch]:
    """Load a `labels.json` file. Format:

    [
      {"t_ms": 1234, "hand": "left", "punch_type": "jab"},
      {"t_ms": 1700, "hand": "right", "punch_type": "cross"},
      ...
    ]
    """
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON array")
    out: list[GroundTruthPunch] = []
    for i, row in enumerate(raw):
        try:
            out.append(
                GroundTruthPunch(
                    t_ms=float(row["t_ms"]),
                    hand=row["hand"],
                    punch_type=row.get("punch_type"),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(f"{path}: row {i} is malformed: {e}") from e
    return out

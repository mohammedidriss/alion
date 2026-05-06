"""Detector evaluation: matching + confusion matrix + report rendering."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from studies import (
    DetectedPunch,
    GroundTruthPunch,
    confusion_matrix,
    match_events,
    render_report,
)
from studies.evaluation import load_labels, per_class_metrics


def _gt(t_ms: float, hand: str = "left", ptype: str | None = None) -> GroundTruthPunch:
    return GroundTruthPunch(t_ms=t_ms, hand=hand, punch_type=ptype)  # type: ignore[arg-type]


def _det(
    t_ms: float, hand: str = "left", ptype: str | None = None, conf: float = 1.0
) -> DetectedPunch:
    return DetectedPunch(t_ms=t_ms, hand=hand, punch_type=ptype, confidence=conf)  # type: ignore[arg-type]


def test_empty_inputs_zero_metrics() -> None:
    r = match_events([], [])
    assert r.true_positives == 0
    assert r.false_positives == 0
    assert r.false_negatives == 0
    assert r.precision == 0.0
    assert r.recall == 0.0
    assert r.f1 == 0.0


def test_perfect_match() -> None:
    truth = [_gt(1000), _gt(2000, "right")]
    det = [_det(1010), _det(2020, "right")]
    r = match_events(truth, det)
    assert r.true_positives == 2
    assert r.false_positives == 0
    assert r.false_negatives == 0
    assert r.precision == 1.0
    assert r.recall == 1.0


def test_outside_tolerance_is_unmatched() -> None:
    # 500 ms apart, default tolerance 200 ms
    truth = [_gt(1000)]
    det = [_det(1500)]
    r = match_events(truth, det)
    assert r.true_positives == 0
    assert r.false_negatives == 1
    assert r.false_positives == 1


def test_hand_mismatch_blocks_match() -> None:
    # Within tolerance but wrong hand
    truth = [_gt(1000, "left")]
    det = [_det(1010, "right")]
    r = match_events(truth, det)
    assert r.true_positives == 0
    assert r.false_negatives == 1
    assert r.false_positives == 1


def test_greedy_picks_closest() -> None:
    # Two detections within tolerance for one truth — pick the closer.
    truth = [_gt(1000)]
    det = [_det(1100), _det(1010)]
    r = match_events(truth, det)
    assert r.true_positives == 1
    assert r.pairs[0].abs_offset_ms == 10
    # The far detection becomes a false positive.
    assert r.false_positives == 1


def test_extra_detection_is_false_positive() -> None:
    truth = [_gt(1000)]
    det = [_det(1010), _det(5000)]
    r = match_events(truth, det)
    assert r.true_positives == 1
    assert r.false_positives == 1
    assert r.recall == 1.0
    assert r.precision == 0.5


def test_confusion_matrix_counts_per_class() -> None:
    truth = [_gt(1000, ptype="jab"), _gt(2000, ptype="hook"), _gt(3000, ptype="jab")]
    det = [
        _det(1010, ptype="jab"),  # correct
        _det(2010, ptype="cross"),  # hook mislabeled as cross
        _det(3010, ptype="jab"),  # correct
    ]
    pairs = match_events(truth, det).pairs
    cm = confusion_matrix(pairs, ["jab", "cross", "hook", "uppercut"])
    assert cm["jab"]["jab"] == 2
    assert cm["hook"]["cross"] == 1
    assert cm["jab"]["cross"] == 0


def test_per_class_metrics() -> None:
    cm = {
        "jab": {"jab": 2, "cross": 0, "hook": 0, "uppercut": 0, "unlabeled": 0},
        "cross": {"jab": 0, "cross": 1, "hook": 0, "uppercut": 0, "unlabeled": 0},
        "hook": {"jab": 0, "cross": 1, "hook": 0, "uppercut": 0, "unlabeled": 0},
        "uppercut": {"jab": 0, "cross": 0, "hook": 0, "uppercut": 0, "unlabeled": 0},
        "unlabeled": {"jab": 0, "cross": 0, "hook": 0, "uppercut": 0, "unlabeled": 0},
    }
    out = per_class_metrics(cm, ["jab", "cross", "hook", "uppercut"])
    # jab: TP=2, FP=0 → P=1.0; FN=0 → R=1.0
    assert out["jab"]["precision"] == 1.0
    assert out["jab"]["recall"] == 1.0
    # cross: TP=1, FP=1 (hook→cross) → P=0.5; FN=0 → R=1.0
    assert out["cross"]["precision"] == 0.5
    assert out["cross"]["recall"] == 1.0
    # hook: TP=0, FN=1 → R=0
    assert out["hook"]["recall"] == 0.0


def test_report_renders_markdown() -> None:
    truth = [_gt(1000, ptype="jab")]
    det = [_det(1020, ptype="jab")]
    r = match_events(truth, det)
    cm = confusion_matrix(r.pairs, ["jab", "cross"])
    out = render_report(r, cm, ["jab", "cross"])
    assert "# Detector evaluation report" in out
    assert "Precision" in out
    assert "Punch-type confusion matrix" in out


def test_load_labels(tmp_path: Path) -> None:
    p = tmp_path / "labels.json"
    p.write_text(
        json.dumps(
            [
                {"t_ms": 100, "hand": "left", "punch_type": "jab"},
                {"t_ms": 250, "hand": "right"},
            ]
        )
    )
    labels = load_labels(p)
    assert len(labels) == 2
    assert labels[0].punch_type == "jab"
    assert labels[1].punch_type is None


def test_load_labels_rejects_malformed(tmp_path: Path) -> None:
    p = tmp_path / "bad.json"
    p.write_text(json.dumps([{"hand": "left"}]))  # missing t_ms
    with pytest.raises(ValueError, match="malformed"):
        load_labels(p)

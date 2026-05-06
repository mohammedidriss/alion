"""CLI: evaluate the punch detector against a manually-labeled video.

Workflow:
  1. Manually label punches in a video → save as labels.json:
     [{"t_ms": 1234, "hand": "left", "punch_type": "jab"}, ...]
  2. Run capture on the same video so detected events land in the DB.
  3. Run this script:
        uv run python scripts/evaluate.py \
            --session <uuid> \
            --labels path/to/labels.json \
            --tolerance-ms 200 \
            --out report.md

Output: per-session precision/recall/F1, punch-type confusion matrix,
and per-class metrics. The report is also written to stdout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID

from sqlmodel import Session, select

from store import PunchEventRow, get_session
from studies import (
    DetectedPunch,
    GroundTruthPunch,
    confusion_matrix,
    match_events,
    render_report,
)
from studies.evaluation import load_labels

PUNCH_CLASSES = ["jab", "cross", "hook", "uppercut"]


def _load_detections(db: Session, session_id: UUID) -> list[DetectedPunch]:
    rows = list(
        db.exec(
            select(PunchEventRow).where(PunchEventRow.session_id == session_id)
        ).all()
    )
    return [
        DetectedPunch(
            t_ms=r.t_ms,
            hand=r.hand.value,  # type: ignore[arg-type]
            punch_type=r.punch_type.value if r.punch_type else None,
            confidence=r.confidence,
        )
        for r in rows
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--session", required=True, help="session UUID in the DB")
    ap.add_argument(
        "--labels", required=True, type=Path, help="path to labels.json"
    )
    ap.add_argument(
        "--tolerance-ms",
        type=float,
        default=200.0,
        help="time-window (ms) for matching detections to truth (default 200)",
    )
    ap.add_argument(
        "--out", type=Path, default=None, help="write the markdown report here"
    )
    args = ap.parse_args()

    truth: list[GroundTruthPunch] = load_labels(args.labels)
    session_id = UUID(args.session)

    with next(get_session()) as db:
        detected = _load_detections(db, session_id)

    if not detected and not truth:
        print("No truth labels and no detections — nothing to evaluate.")
        return 0

    result = match_events(truth, detected, tolerance_ms=args.tolerance_ms)
    cm = confusion_matrix(result.pairs, PUNCH_CLASSES)
    report = render_report(result, cm, PUNCH_CLASSES, tolerance_ms=args.tolerance_ms)

    print(report)
    if args.out:
        args.out.write_text(report)
        print(f"\nReport written to {args.out}", file=sys.stderr)

    # Summary line for quick eyeballing
    print(
        f"\n[summary] P={result.precision:.3f} R={result.recall:.3f} "
        f"F1={result.f1:.3f} (TP={result.true_positives} "
        f"FP={result.false_positives} FN={result.false_negatives})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

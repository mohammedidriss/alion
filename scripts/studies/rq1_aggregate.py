"""RQ1 aggregation — pull rater scores out of the DB into a flat CSV.

Output format:
    session_id,payload_mode,rater_id,criterion,score,created_at

Run:
    uv run python -m scripts.studies.rq1_aggregate \
        --out data/studies/rq1_ratings.csv

The CSV is the input to `rq1_stats.py` and to any downstream R/SPSS
analysis the dissertation pulls into.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from sqlmodel import select

from store import RaterScoreRow, get_session


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("data/studies/rq1_ratings.csv"))
    ap.add_argument(
        "--session-ids",
        nargs="*",
        default=None,
        help=(
            "Optional explicit allow-list of session UUIDs. When omitted the "
            "export pulls every rating in the database."
        ),
    )
    ap.add_argument("--rater-id", default=None, help="Filter by rater id.")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    gen = get_session()
    db = next(gen)
    try:
        stmt = select(RaterScoreRow)
        if args.rater_id:
            stmt = stmt.where(RaterScoreRow.rater_id == args.rater_id)  # type: ignore[arg-type]
        rows = list(db.exec(stmt).all())
    finally:
        try:
            next(gen)
        except StopIteration:
            pass

    allow = set(args.session_ids) if args.session_ids else None
    if allow:
        rows = [r for r in rows if str(r.session_id) in allow]

    with args.out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "session_id",
                "payload_mode",
                "rater_id",
                "criterion",
                "score",
                "created_at",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    str(r.session_id),
                    r.payload_mode.value
                    if hasattr(r.payload_mode, "value")
                    else str(r.payload_mode),
                    r.rater_id,
                    r.criterion,
                    r.score,
                    r.created_at.isoformat() if r.created_at else "",
                ]
            )

    print(f"wrote {len(rows)} rating rows to {args.out}")


if __name__ == "__main__":
    main()

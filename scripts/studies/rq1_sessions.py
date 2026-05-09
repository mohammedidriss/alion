"""RQ1 sample-selection query.

Returns the session ids that meet the inclusion criteria for the RQ1
rater study:

  • status = completed
  • round_count is set (i.e. the session was structured)
  • duration_ms > 0 (capture actually ran)
  • at least one CV punch event
  • at least one HRV sample
  • at least one IMU sample (synth is fine pre-Polar)

Run:
    uv run python -m scripts.studies.rq1_sessions

Pipe into rq1_aggregate.py:
    uv run python -m scripts.studies.rq1_sessions \
        | xargs uv run python -m scripts.studies.rq1_aggregate --session-ids
"""

from __future__ import annotations

import argparse

from sqlmodel import select

from store import (
    HRSampleRow,
    IMUSampleRow,
    PunchEventRow,
    Session,
    SessionStatus,
    get_session,
)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--require-imu",
        action="store_true",
        default=True,
        help="Require at least one IMU sample (default: true).",
    )
    ap.add_argument(
        "--no-require-imu",
        dest="require_imu",
        action="store_false",
    )
    args = ap.parse_args()

    gen = get_session()
    db = next(gen)
    try:
        sessions = list(
            db.exec(select(Session).where(Session.status == SessionStatus.COMPLETED)).all()  # type: ignore[arg-type]
        )

        eligible: list[str] = []
        for s in sessions:
            if not s.round_count or s.duration_ms <= 0:
                continue
            cv = (
                db.exec(
                    select(PunchEventRow).where(PunchEventRow.session_id == s.id).limit(1)  # type: ignore[arg-type]
                ).first()
                is not None
            )
            hrv = (
                db.exec(
                    select(HRSampleRow).where(HRSampleRow.session_id == s.id).limit(1)  # type: ignore[arg-type]
                ).first()
                is not None
            )
            imu = (
                db.exec(
                    select(IMUSampleRow).where(IMUSampleRow.session_id == s.id).limit(1)  # type: ignore[arg-type]
                ).first()
                is not None
            )
            if cv and hrv and (imu or not args.require_imu):
                eligible.append(str(s.id))

        for sid in eligible:
            print(sid)
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


if __name__ == "__main__":
    main()

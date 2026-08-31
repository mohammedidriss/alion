"""HeadImpactRepo round-trip — head_impact_event table (ADR 007)."""

from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session

from store import HeadImpactEventRow, HeadImpactRepo, ImpactLocationEnum


def _row(session_id, t_ms: float, location: ImpactLocationEnum) -> HeadImpactEventRow:
    return HeadImpactEventRow(
        session_id=session_id,
        t_ms=t_ms,
        peak_linear_accel_g=40.0,
        peak_rotational_vel_rad_s=15.0,
        peak_rotational_accel_rad_s2=3000.0,
        location=location,
        device_id="MG-1",
        confidence=0.9,
    )


def test_add_many_and_list_ordered(session: Session) -> None:
    repo = HeadImpactRepo(session)
    sid = uuid4()
    # Insert out of order; list must come back ordered by t_ms.
    repo.add_many(
        [
            _row(sid, 900.0, ImpactLocationEnum.FRONT),
            _row(sid, 100.0, ImpactLocationEnum.CHIN),
            _row(sid, 500.0, ImpactLocationEnum.LEFT),
        ]
    )
    rows = repo.list_for_session(sid)
    assert [r.t_ms for r in rows] == [100.0, 500.0, 900.0]
    assert rows[0].location == ImpactLocationEnum.CHIN
    assert repo.count_for_session(sid) == 3


def test_scoped_to_session(session: Session) -> None:
    repo = HeadImpactRepo(session)
    a, b = uuid4(), uuid4()
    repo.add_many([_row(a, 1.0, ImpactLocationEnum.TOP)])
    repo.add_many([_row(b, 2.0, ImpactLocationEnum.BACK), _row(b, 3.0, ImpactLocationEnum.RIGHT)])
    assert repo.count_for_session(a) == 1
    assert repo.count_for_session(b) == 2


def test_replace_for_session(session: Session) -> None:
    repo = HeadImpactRepo(session)
    sid = uuid4()
    repo.add_many(
        [_row(sid, 1.0, ImpactLocationEnum.FRONT), _row(sid, 2.0, ImpactLocationEnum.BACK)]
    )
    n = repo.replace_for_session(sid, [_row(sid, 9.0, ImpactLocationEnum.CHIN)])
    assert n == 1
    rows = repo.list_for_session(sid)
    assert len(rows) == 1
    assert rows[0].t_ms == 9.0
    assert rows[0].location == ImpactLocationEnum.CHIN


def test_optional_rotational_accel_nullable(session: Session) -> None:
    repo = HeadImpactRepo(session)
    sid = uuid4()
    row = _row(sid, 1.0, ImpactLocationEnum.FRONT)
    row.peak_rotational_accel_rad_s2 = None
    repo.add_many([row])
    stored = repo.list_for_session(sid)[0]
    assert stored.peak_rotational_accel_rad_s2 is None

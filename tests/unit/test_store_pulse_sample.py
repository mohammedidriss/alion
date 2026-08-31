"""PulseSampleRepo round-trip — pulse_sample table, kept separate from HRV (ADR 008)."""

from __future__ import annotations

from uuid import uuid4

from sqlmodel import Session, select

from store import (
    CardiacSourceEnum,
    HRSampleRow,
    PulseSampleRepo,
    PulseSampleRow,
)


def _row(session_id, t_ms: float, ibi_ms: float) -> PulseSampleRow:
    return PulseSampleRow(
        session_id=session_id,
        t_ms=t_ms,
        ibi_ms=ibi_ms,
        pulse_bpm=60_000.0 / ibi_ms,
        quality=0.8,
    )


def test_add_many_and_list_ordered(session: Session) -> None:
    repo = PulseSampleRepo(session)
    sid = uuid4()
    repo.add_many([_row(sid, 900.0, 820.0), _row(sid, 100.0, 800.0), _row(sid, 500.0, 810.0)])
    rows = repo.list_for_session(sid)
    assert [r.t_ms for r in rows] == [100.0, 500.0, 900.0]
    assert repo.count_for_session(sid) == 3
    assert all(r.source == CardiacSourceEnum.RPPG for r in rows)


def test_default_source_is_rppg(session: Session) -> None:
    repo = PulseSampleRepo(session)
    sid = uuid4()
    repo.add_many([_row(sid, 1.0, 800.0)])
    assert repo.list_for_session(sid)[0].source == CardiacSourceEnum.RPPG


def test_pulse_samples_do_not_touch_hr_sample(session: Session) -> None:
    """rPPG PRV must never leak into the ECG-HRV (hr_sample) table."""
    repo = PulseSampleRepo(session)
    sid = uuid4()
    repo.add_many([_row(sid, 1.0, 800.0), _row(sid, 2.0, 810.0)])
    hr_rows = session.exec(select(HRSampleRow).where(HRSampleRow.session_id == sid)).all()
    assert list(hr_rows) == []  # nothing written to the HRV stream


def test_replace_for_session(session: Session) -> None:
    repo = PulseSampleRepo(session)
    sid = uuid4()
    repo.add_many([_row(sid, 1.0, 800.0), _row(sid, 2.0, 810.0)])
    n = repo.replace_for_session(sid, [_row(sid, 9.0, 790.0)])
    assert n == 1
    rows = repo.list_for_session(sid)
    assert len(rows) == 1
    assert rows[0].t_ms == 9.0


def test_session_delete_cascades_to_new_sensor_tables(session: Session) -> None:
    """Deleting a session removes its head-impact and pulse rows (no orphans)."""
    from store import (
        FighterRepo,
        HeadImpactEventRow,
        HeadImpactRepo,
        ImpactLocationEnum,
        SessionRepo,
    )
    from store.models import FighterCreate, SessionCreate, SessionSourceEnum

    fighter = FighterRepo(session).create(FighterCreate(name="Cascade"))
    sess = SessionRepo(session).create(
        SessionCreate(fighter_id=fighter.id, source=SessionSourceEnum.HRV_REPLAY)
    )

    PulseSampleRepo(session).add_many([_row(sess.id, 1.0, 800.0)])
    HeadImpactRepo(session).add_many(
        [
            HeadImpactEventRow(
                session_id=sess.id,
                t_ms=1.0,
                peak_linear_accel_g=40.0,
                peak_rotational_vel_rad_s=15.0,
                location=ImpactLocationEnum.CHIN,
                confidence=0.9,
            )
        ]
    )
    assert PulseSampleRepo(session).count_for_session(sess.id) == 1
    assert HeadImpactRepo(session).count_for_session(sess.id) == 1

    assert SessionRepo(session).delete(sess.id) is True
    assert PulseSampleRepo(session).count_for_session(sess.id) == 0
    assert HeadImpactRepo(session).count_for_session(sess.id) == 0

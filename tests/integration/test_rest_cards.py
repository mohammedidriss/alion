"""Rest cards (ADR-041): the facts ledger, the three template cards, a model's
phrasing kept only where every number and word checks out, the record of it,
and the coach's taps (ADR-043)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from store import AdviceRecord, HRSampleRow, RestHRSampleRow
from tests.integration.test_cross_check import _imu_rows

ROUND_MS = 60_000


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.routes import capture_coord
    from api.services import session_analysis

    monkeypatch.setattr(session_analysis, "POSE_DIR", tmp_path / "pose")
    monkeypatch.setattr(capture_coord, "_VIDEO_DIR", tmp_path / "clips")
    monkeypatch.setattr(capture_coord, "_STATE_DIR", tmp_path / "capture")
    (tmp_path / "pose").mkdir()
    (tmp_path / "clips").mkdir()
    yield tmp_path


def _beats(sid: UUID, start_ms: float, end_ms: float, bpm: float) -> list[HRSampleRow]:
    rr = 60_000.0 / bpm
    out, t = [], start_ms
    while t < end_ms:
        out.append(HRSampleRow(session_id=sid, t_ms=t, rr_ms=rr, hr_bpm=bpm))
        t += rr
    return out


def _rest(
    sid: UUID, bell_ms: float, began: float, start_bpm: float, end_bpm: float
) -> list[RestHRSampleRow]:
    """30 s of rest, heart rate falling linearly."""
    out, t = [], 0.0
    while t <= 30_000:
        bpm = start_bpm + (end_bpm - start_bpm) * t / 30_000
        out.append(
            RestHRSampleRow(
                session_id=sid,
                pause_started_ms=began,
                at_ms=bell_ms,
                rest_ms=t,
                rr_ms=60_000.0 / bpm,
                hr_bpm=bpm,
            )
        )
        t += 60_000.0 / bpm
    return out


@pytest.fixture
def sid(authed_client: TestClient, session: Session, dirs: Path) -> str:
    from store import Session as SessionRow

    fid = authed_client.post("/fighters", json={"name": "Rest", "stance": "orthodox"}).json()["id"]
    s = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
        "id"
    ]
    authed_client.patch(
        f"/sessions/{s}", json={"round_count": 3, "round_duration_s": 60, "rest_duration_s": 30}
    )
    sid_ = UUID(s)
    # Round 1: 8 left, 4 right. Round 2: 4 left, 2 right — output halves.
    left = [3_000 + 7_000 * i for i in range(8)] + [63_000 + 14_000 * i for i in range(4)]
    right = [6_000 + 14_000 * i for i in range(4)] + [70_000 + 25_000 * i for i in range(2)]
    session.add_all(
        _imu_rows(sid_, {"left": left, "right": right}, {"left": 120_000, "right": 120_000})
    )
    session.add_all(_beats(sid_, 0, ROUND_MS, 150) + _beats(sid_, ROUND_MS, 2 * ROUND_MS, 160))
    # Rest 1: 150 → 120 in 30 s. Rest 2: 160 → 145 — slower.
    session.add_all(_rest(sid_, ROUND_MS, 1e6, 150, 120) + _rest(sid_, 2 * ROUND_MS, 2e6, 160, 145))
    row = session.get(SessionRow, sid_)
    assert row is not None
    row.duration_ms = 2 * ROUND_MS
    session.add(row)
    session.commit()
    return s


def test_the_ledger_and_the_three_template_cards(authed_client: TestClient, sid: str) -> None:
    ex = authed_client.get(f"/sessions/{sid}/rounds_export").json()
    r1, r2 = ex["rounds"][0], ex["rounds"][1]
    assert r1["rest"]["drop_30s"] > r2["rest"]["drop_30s"] > 0  # recovery slowed
    assert r2["coverage"]["wrist_left"] == pytest.approx(1.0, abs=0.01)
    assert r1["imu"]["clipped"] == 0

    out = authed_client.get(f"/sessions/{sid}/rest_cards", params={"after_round": 2}).json()
    facts = {f["what"]: f for f in out["facts"]}
    assert facts["punches"]["value"] == 6 and facts["punches"]["evidence"] == "thrown"
    change = facts["output_vs_previous"]
    assert change["direction"] == "down" and change["value"] == 50 and change["previous_round"] == 1
    assert facts["mean_hr"]["value"] == 160 and facts["mean_hr"]["direction"] == "up"
    assert facts["recovery_vs_previous"]["direction"] == "down"
    assert {f["hand"] for f in out["facts"] if f["kind"] == "hands"} == {"lead", "rear"}
    assert len(out["facts_sha256"]) == 64

    cards = {c["slot"]: c for c in out["cards"]}
    assert [c["slot"] for c in out["cards"]] == ["opportunity", "warning", "recovery"]
    assert cards["warning"]["headline"] == "Output down 50% on round 1"
    assert cards["warning"]["fact_ids"] == [change["id"]]
    assert cards["recovery"]["headline"].startswith("Heart rate down")
    assert "slower than round 1" in (cards["recovery"]["context"] or "")
    assert all(c["source"] == "template" and c["shape"] for c in out["cards"])


def _fake(monkeypatch: pytest.MonkeyPatch, output: dict[str, Any] | None) -> list[str]:
    import coach

    calls: list[str] = []

    async def fake(
        system: str, user: str, schema: dict[str, Any], *, timeout_s: float = 12.0
    ) -> dict[str, Any] | None:
        calls.append(user)
        return output

    monkeypatch.setattr(coach, "generate_json", fake)
    return calls


def test_a_models_cards_replace_templates_only_where_they_check_out(
    authed_client: TestClient, session: Session, sid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    facts = {
        f["what"]: f
        for f in authed_client.get(f"/sessions/{sid}/rest_cards", params={"after_round": 2}).json()[
            "facts"
        ]
    }
    change, rest = facts["output_vs_previous"], facts["hr_drop_30s"]
    _fake(
        monkeypatch,
        {
            "cards": [
                {
                    "slot": "warning",
                    "headline": "Output fell 50% from round 1",
                    "detail": "punches per minute",
                    "cites": [change["id"]],
                },
                # A number the facts don't hold: dropped, the template stays.
                {
                    "slot": "recovery",
                    "headline": "Heart rate down 99 bpm",
                    "detail": "",
                    "cites": [rest["id"]],
                },
                # Says "landed": the sensors only count thrown.
                {
                    "slot": "opportunity",
                    "headline": "Jabs landed well",
                    "detail": "",
                    "cites": [change["id"]],
                },
            ]
        },
    )
    out = authed_client.post(f"/sessions/{sid}/rest_cards", json={"after_round": 2}).json()
    cards = {c["slot"]: c for c in out["cards"]}
    assert (
        cards["warning"]["source"] == "model"
        and cards["warning"]["headline"] == "Output fell 50% from round 1"
    )
    assert cards["recovery"]["source"] == "template"
    assert cards["opportunity"]["source"] == "template"
    gates = {v["slot"]: v["gate"] for v in out["verdicts"]}
    assert gates["warning"] is None
    assert gates["recovery"].startswith("numbers")
    assert gates["opportunity"].startswith("evidence")
    rec = session.exec(select(AdviceRecord).where(AdviceRecord.kind == "rest_cards")).one()
    assert rec.status == "shown" and str(rec.id) == out["advice_id"]
    assert out["facts_sha256"] in rec.output_json


def test_no_model_means_the_templates_and_a_failed_record(
    authed_client: TestClient, session: Session, sid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fake(monkeypatch, None)
    out = authed_client.post(f"/sessions/{sid}/rest_cards", json={"after_round": 1}).json()
    assert all(c["source"] == "template" for c in out["cards"]) and out["verdicts"] is None
    assert session.exec(select(AdviceRecord)).one().status == "failed"


def test_the_coach_logs_what_they_did_with_the_cards(authed_client: TestClient, sid: str) -> None:
    url = f"/sessions/{sid}/rest_cards/feedback"
    r = authed_client.post(
        url,
        json={"after_round": 1, "slot": "own_read", "action": "own_read", "note": "Hands dropping"},
    )
    assert r.status_code == 201
    r = authed_client.post(
        url, json={"after_round": 1, "slot": "warning", "action": "noted", "fact_ids": ["F2"]}
    )
    assert r.status_code == 201
    assert (
        authed_client.post(
            url, json={"after_round": 1, "slot": "warning", "action": "own_read"}
        ).status_code
        == 422
    )
    got = authed_client.get(url).json()
    assert [(g["slot"], g["action"]) for g in got] == [
        ("own_read", "own_read"),
        ("warning", "noted"),
    ]
    assert got[0]["note"] == "Hands dropping" and got[1]["fact_ids"] == ["F2"]


def test_a_coach_only_study_session_gets_no_cards(authed_client: TestClient, sid: str) -> None:
    authed_client.patch(f"/sessions/{sid}", json={"study_condition": "coach_only"})
    assert (
        authed_client.get(f"/sessions/{sid}/rest_cards", params={"after_round": 1}).status_code
        == 403
    )


def test_beats_in_a_pause_are_kept_for_recovery(session: Session, dirs: Path) -> None:
    from contextlib import contextmanager
    from uuid import uuid4

    from api.routes import capture_coord, hrv

    capture_id = uuid4()
    start = 1_000_000.0
    c = capture_coord._ensure(capture_id)
    c.command, c.last_start_ms, c.pauses = "start", start, [[start + 60_000, None]]
    assert capture_coord.pause_at_ms(capture_id, start + 70_000) == (start + 60_000, 60_000, 10_000)
    assert capture_coord.timeline_at_ms(capture_id, start + 70_000) is None

    @contextmanager
    def factory() -> Iterator[Session]:
        yield session

    write = hrv._on_camera_timeline(capture_id, factory)
    write(
        [
            HRSampleRow(session_id=capture_id, t_ms=start + 30_000, rr_ms=400, hr_bpm=150),
            HRSampleRow(session_id=capture_id, t_ms=start + 75_000, rr_ms=450, hr_bpm=133),
        ]
    )
    kept = session.exec(select(HRSampleRow).where(HRSampleRow.session_id == capture_id)).all()
    rest = session.exec(
        select(RestHRSampleRow).where(RestHRSampleRow.session_id == capture_id)
    ).all()
    assert [r.t_ms for r in kept] == [30_000]
    assert [(r.at_ms, r.rest_ms, r.hr_bpm) for r in rest] == [(60_000, 15_000, 133)]


def test_an_idle_session_has_no_streams_to_judge(authed_client: TestClient, sid: str) -> None:
    r = authed_client.get(f"/v2/sessions/{sid}/streams")
    assert r.status_code == 200 and r.json() == []

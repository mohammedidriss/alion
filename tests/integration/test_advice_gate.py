"""Every piece of AI advice is safety-checked and recorded before it's shown
(ADR-018): blocked advice is withheld and logged, never cached; nothing that
names the fighter goes to the model."""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from coach import WITHHELD, CoachAdvice
from store import AdviceRecord


class FakeLLM:
    def __init__(self, summary: str, items: list[str] | None = None) -> None:
        self.summary, self.items = summary, items or ["Double the jab"]
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, system_prompt: str, user_content: str) -> CoachAdvice:
        self.calls.append((system_prompt, user_content))
        return CoachAdvice(summary=self.summary, action_items=list(self.items))


@pytest.fixture
def fighter_session(authed_client: TestClient) -> tuple[str, str]:
    fid = authed_client.post(
        "/fighters", json={"name": "Sami Haddad", "stance": "orthodox"}
    ).json()["id"]
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
        "id"
    ]
    return fid, sid


def _use(monkeypatch: pytest.MonkeyPatch, llm: Any) -> None:
    import coach

    monkeypatch.setattr(coach, "generate_corner_advice", llm)


def test_advice_with_a_medical_judgement_is_withheld_logged_and_not_cached(
    authed_client: TestClient,
    session: Session,
    fighter_session: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, sid = fighter_session
    llm = FakeLLM("Looks like a concussion — stop the fight.")
    _use(monkeypatch, llm)
    r = authed_client.post(f"/sessions/{sid}/advice").json()
    assert r["status"] == "withheld" and r["summary"] == WITHHELD and r["action_items"] == []
    rec = session.exec(select(AdviceRecord)).one()
    assert rec.status == "withheld" and rec.kind == "corner"
    assert json.loads(rec.blocked_terms) == ["concussion", "stop the fight"]
    assert "concussion" in rec.output_json  # kept for review
    assert rec.model and rec.prompt_sha256 and rec.input_sha256 and rec.output_sha256
    # Not cached: asking again goes back to the model.
    authed_client.post(f"/sessions/{sid}/advice")
    assert len(llm.calls) == 2


def test_training_advice_is_shown_recorded_and_cached(
    authed_client: TestClient,
    session: Session,
    fighter_session: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, sid = fighter_session
    llm = FakeLLM("Good volume; your output dropped in round 3.", ["Pace round 3"])
    _use(monkeypatch, llm)
    r = authed_client.post(f"/sessions/{sid}/advice").json()
    assert r["status"] == "shown" and r["action_items"] == ["Pace round 3"] and r["advice_id"]
    assert session.exec(select(AdviceRecord)).one().status == "shown"
    authed_client.post(f"/sessions/{sid}/advice")
    assert len(llm.calls) == 1  # the cache answered


def test_a_failed_model_call_is_recorded_as_failed_and_not_cached(
    authed_client: TestClient,
    session: Session,
    fighter_session: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, sid = fighter_session
    _use(monkeypatch, FakeLLM("Failed to connect to LLM (x at y): refused", []))
    assert authed_client.post(f"/sessions/{sid}/advice").json()["status"] == "failed"
    assert session.exec(select(AdviceRecord)).one().status == "failed"


def test_weight_advice_is_gated_and_the_model_never_gets_the_name(
    authed_client: TestClient,
    session: Session,
    fighter_session: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fid, _ = fighter_session
    for kg in (70.0, 71.4, 69.2):
        assert (
            authed_client.post(f"/fighters/{fid}/weigh-ins", json={"weight_kg": kg}).status_code
            == 201
        )
    llm = FakeLLM("Rapid loss, signs of dehydration.")
    _use(monkeypatch, llm)
    r = authed_client.get(f"/fighters/{fid}/weight-analysis").json()
    assert (
        r["ai_status"] == "withheld"
        and r["ai_summary"] == WITHHELD
        and r["ai_recommendations"] == []
    )
    system_prompt, user_content = llm.calls[0]
    assert "Sami" not in user_content and "Haddad" not in user_content
    assert "dehydration" not in system_prompt.split("Safety rules")[0]
    rec = session.exec(select(AdviceRecord)).one()
    assert rec.kind == "weight" and rec.fighter_id is not None and rec.status == "withheld"

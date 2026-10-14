"""Advice only, never medical (ADR-039): stored and frozen advice is checked again
each time it's shown, a reply is checked even when it looks like a failure, and
study advice can't carry medical wording to reviewers."""

from __future__ import annotations

import json
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from coach import WITHHELD
from store import AdviceRecord, CoachAdviceCacheRow
from store.models import StudyAdviceClaimRow, StudyAdviceSnapshotRow
from tests.integration.test_advice_gate import FakeLLM, _use
from tests.integration.test_api_reliance import BASE, _snapshot


@pytest.fixture
def sid(authed_client: TestClient) -> str:
    fid = authed_client.post("/fighters", json={"name": "Amir", "stance": "orthodox"}).json()["id"]
    return str(
        authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
            "id"
        ]
    )


def test_cached_advice_is_checked_again_when_shown(
    authed_client: TestClient,
    session: Session,
    sid: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, FakeLLM("Keep the jab busy.", ["Double the jab"]))
    assert authed_client.post(f"/sessions/{sid}/advice").json()["status"] == "shown"
    # Advice cached before a term joined the list: it's stopped the next time.
    row = session.exec(select(CoachAdviceCacheRow)).one()
    row.action_items_json = json.dumps(["Take ibuprofen after the round"])
    session.add(row)
    session.commit()
    r = authed_client.post(f"/sessions/{sid}/advice").json()
    assert r["status"] == "withheld" and r["summary"] == WITHHELD and r["action_items"] == []


def test_frozen_advice_is_checked_again_when_shown(
    authed_client: TestClient,
    session: Session,
    sid: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, FakeLLM("Keep the jab busy.", ["Double the jab"]))
    authed_client.post(f"/sessions/{sid}/advice")
    authed_client.post(f"/sessions/{sid}/advice/lock")
    rec = session.exec(select(AdviceRecord).where(AdviceRecord.locked)).one()
    rec.output_json = json.dumps({"summary": "Signs of a heart problem.", "action_items": []})
    session.add(rec)
    session.commit()
    r = authed_client.post(f"/sessions/{sid}/advice").json()
    assert r["status"] == "withheld" and r["summary"] == WITHHELD and r["locked"] is True


def test_a_reply_that_looks_like_a_failure_is_still_checked(
    authed_client: TestClient,
    session: Session,
    sid: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, FakeLLM("Failed to connect to LLM — but it looks like a concussion."))
    r = authed_client.post(f"/sessions/{sid}/advice").json()
    assert r["status"] == "withheld" and "concussion" not in r["summary"]
    assert session.exec(select(AdviceRecord)).one().status == "withheld"


def test_study_advice_with_medical_wording_is_refused(authed_client: TestClient) -> None:
    fid = authed_client.post("/fighters", json={"name": "Study X"}).json()["id"]
    sid_ = authed_client.post(
        "/sessions", json={"fighter_id": fid, "source": "live_webcam"}
    ).json()["id"]
    body = {
        "session_id": sid_,
        "payload_mode": "fused",
        "model_id": "gemma3:4b",
        "prompt_version": "v4",
        "prompt_text": "Training-only prompt",
        "input_payload": {"round": 1},
        "summary": "Pace the third round.",
        "action_items": ["Return the lead hand to guard."],
        "correctness": "incorrect",
        "adjudication_note": "Two adjudicators agreed.",
        "claims": [
            {
                "claim_text": "Possible concussion after the hook.",
                "evidence": {"t_ms": 1200},
                "source_stream": "cv",
                "evidence_quality": "validated",
            }
        ],
    }
    r = authed_client.post(f"{BASE}/snapshots", json=body)
    assert r.status_code == 422 and "concussion" in r.json()["detail"]


def test_reviewers_never_see_study_advice_that_reads_as_medical(
    authed_client: TestClient, session: Session
) -> None:
    from api.routes.reliance import _advisory

    snap_id = _snapshot(authed_client, "correct", 1)
    snap = session.get(StudyAdviceSnapshotRow, UUID(snap_id))
    assert snap is not None
    assert _advisory(session, snap).summary == "Advisory 1"
    claim = session.exec(select(StudyAdviceClaimRow)).one()
    claim.claim_text = "Shows symptoms of fatigue-related injury."
    session.add(claim)
    session.commit()
    shown = _advisory(session, snap)
    assert shown.summary == WITHHELD and shown.action_items == [] and shown.claims == []

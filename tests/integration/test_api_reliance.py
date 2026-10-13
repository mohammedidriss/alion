"""The appropriate-reliance study (ADR-026): enrolment, the server-run sequence,
blinding, final decisions and the export."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from store.models import RelianceTrialRow, TrustSurveyRow
from tests.conftest import _signed_in

BASE = "/v2/studies/reliance"


@pytest.fixture
def ready_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A questionnaire with its wording in place (the shipped file is placeholders)."""
    path = tmp_path / "items.json"
    path.write_text(
        json.dumps(
            {
                "instrument": "Test checklist",
                "scale": {"min": 1, "max": 7, "low": "Not at all", "high": "Extremely"},
                "distrust": [{"id": "d1", "text": "Wary"}, {"id": "d2", "text": "Suspicious"}],
                "trust": [{"id": "t1", "text": "Reliable"}, {"id": "t2", "text": "Dependable"}],
            }
        )
    )
    monkeypatch.setenv("ALION_TRUST_ITEMS_FILE", str(path))
    yield path


def _snapshot(client: TestClient, correctness: str, n: int) -> str:
    fid = client.post("/fighters", json={"name": f"Study {n}"}).json()["id"]
    sid = client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    r = client.post(
        f"{BASE}/snapshots",
        json={
            "session_id": sid,
            "payload_mode": "fused",
            "model_id": "gemma3:4b",
            "prompt_version": "v3",
            "prompt_text": "Training-only prompt",
            "input_payload": {"round": 1, "punches": 12 + n},
            "summary": f"Advisory {n}",
            "action_items": ["Return the lead hand to guard."],
            "correctness": correctness,
            "adjudication_note": "Two adjudicators agreed.",
            "claims": [
                {
                    "claim_text": "Lead-hand recovery is slow.",
                    "evidence": {"t_ms": 1200, "wrist_velocity_ms": 4.1},
                    "source_stream": "cv",
                    "source_start_ms": 1100,
                    "source_end_ms": 1400,
                    "evidence_quality": "validated",
                }
            ],
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _reviewer(client: TestClient, email: str = "rev@alion.test") -> dict[str, str]:
    """A coach who signs up, then is enrolled by the researcher."""
    token = _signed_in(client, email, "Reviewer", "coach")
    r = client.post(f"{BASE}/reviewers", json={"email": email.upper()})  # any case
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {token}"}


def _answers(step: dict[str, Any], score: int = 5) -> dict[str, dict[str, int]]:
    ins = step["instrument"]
    return {
        "trust_items": {i["id"]: score for i in ins["trust"]},
        "distrust_items": {i["id"]: 8 - score for i in ins["distrust"]},
    }


def test_only_researchers_enrol_and_only_enrolled_reviewers_take_part(
    authed_client: TestClient, ready_items: Path
) -> None:
    other = _signed_in(authed_client, "other@alion.test", "Other", "coach")
    as_other = {"Authorization": f"Bearer {other}"}
    # A coach who isn't enrolled can't take part, or enrol anyone.
    assert authed_client.get(f"{BASE}/me", headers=as_other).status_code == 403
    r = authed_client.post(
        f"{BASE}/reviewers", json={"email": "other@alion.test"}, headers=as_other
    )
    assert r.status_code == 403
    # Fighters aren't reviewers.
    _signed_in(authed_client, "fighter@alion.test", "F", "fighter")
    assert (
        authed_client.post(f"{BASE}/reviewers", json={"email": "fighter@alion.test"}).status_code
        == 422
    )
    # The researcher enrols the coach: a study code, once.
    r = authed_client.post(f"{BASE}/reviewers", json={"email": "other@alion.test"})
    assert r.status_code == 201 and r.json()["reviewer_code"] == "RV-001"
    assert (
        authed_client.post(f"{BASE}/reviewers", json={"email": "other@alion.test"}).status_code
        == 409
    )
    assert authed_client.get(f"{BASE}/me", headers=as_other).json()["reviewer_code"] == "RV-001"


def test_the_server_runs_the_sequence_and_never_reveals_correctness(
    authed_client: TestClient, session: Session, ready_items: Path
) -> None:
    kinds = ["correct", "incorrect", "correct", "correct", "correct"]
    ids = {_snapshot(authed_client, c, n): c for n, c in enumerate(kinds)}
    me = _reviewer(authed_client)

    labels, seen = [], []
    for _ in range(20):
        body = authed_client.get(f"{BASE}/me", headers=me).json()
        step = body["step"]
        labels.append(step["label"])
        text = json.dumps(body)
        assert "correctness" not in text and "session_id" not in text and "post_error" not in text
        if step["kind"] == "survey":
            r = authed_client.post(f"{BASE}/surveys", json=_answers(step), headers=me)
            assert r.status_code == 201, r.text
        elif step["kind"] == "trial":
            adv = step["advisory"]
            seen.append(adv["id"])
            claim = adv["claims"][0]["id"]
            assert (
                authed_client.post(f"{BASE}/claims/{claim}/trace-opens", headers=me).status_code
                == 201
            )
            r = authed_client.post(
                f"{BASE}/snapshots/{adv['id']}/trials",
                json={"decision": "follow", "response_ms": 4200},
                headers=me,
            )
            assert r.status_code == 201, r.text
        else:
            break
    assert sorted(seen) == sorted(ids)  # every advisory, once
    assert labels[0] == "Check-in 1" and labels[-1] == "All done"

    code = "RV-001"
    trials = session.exec(
        select(RelianceTrialRow).where(RelianceTrialRow.reviewer_code == code)
    ).all()
    surveys = {
        str(s.timepoint): s.after_trials
        for s in session.exec(
            select(TrustSurveyRow).where(TrustSurveyRow.reviewer_code == code)
        ).all()
    }
    error_at = next(t.position for t in trials if ids[str(t.snapshot_id)] == "incorrect")
    assert surveys["pre_exposure"] == 0
    assert surveys["post_error"] == error_at  # right after the incorrect advisory
    correct_after = sorted(
        t.position for t in trials if t.position > error_at and ids[str(t.snapshot_id)] == "correct"
    )
    expected_recovery = correct_after[1] if len(correct_after) >= 2 else len(kinds)
    assert surveys["post_recovery"] == expected_recovery


def test_decisions_are_final_and_follow_the_order(
    authed_client: TestClient, ready_items: Path
) -> None:
    a = _snapshot(authed_client, "correct", 0)
    b = _snapshot(authed_client, "correct", 1)
    me = _reviewer(authed_client)
    step = authed_client.get(f"{BASE}/me", headers=me).json()["step"]
    # The opening check-in comes first: no decision yet.
    r = authed_client.post(
        f"{BASE}/snapshots/{a}/trials", json={"decision": "follow", "response_ms": 1}, headers=me
    )
    assert r.status_code == 409
    # Every item must be answered, on the scale.
    bad = _answers(step)
    bad["trust_items"]["t1"] = 9
    assert authed_client.post(f"{BASE}/surveys", json=bad, headers=me).status_code == 422
    partial = _answers(step)
    partial["trust_items"].pop("t2")
    assert authed_client.post(f"{BASE}/surveys", json=partial, headers=me).status_code == 422
    assert authed_client.post(f"{BASE}/surveys", json=_answers(step), headers=me).status_code == 201
    assert authed_client.post(f"{BASE}/surveys", json=_answers(step), headers=me).status_code == 409

    due = authed_client.get(f"{BASE}/me", headers=me).json()["step"]["advisory"]["id"]
    other = b if due == a else a
    r = authed_client.post(
        f"{BASE}/snapshots/{other}/trials",
        json={"decision": "reject", "response_ms": 1},
        headers=me,
    )
    assert r.status_code == 409  # not the one that's due
    ok = {"decision": "adjust", "response_ms": 3000, "rationale": "  "}
    assert (
        authed_client.post(f"{BASE}/snapshots/{due}/trials", json=ok, headers=me).status_code == 201
    )
    assert (
        authed_client.post(f"{BASE}/snapshots/{due}/trials", json=ok, headers=me).status_code == 409
    )


def test_the_study_stays_closed_until_the_wording_is_in(authed_client: TestClient) -> None:
    _snapshot(authed_client, "correct", 0)
    me = _reviewer(authed_client)
    body = authed_client.get(f"{BASE}/me", headers=me).json()
    assert body["ready"] is False  # the shipped file still has '[paste …]' items
    assert authed_client.get(f"{BASE}/instrument").json()["ready"] is False
    r = authed_client.post(f"{BASE}/surveys", json=_answers(body["step"]), headers=me)
    assert r.status_code == 409


def test_the_export_classifies_each_decision(authed_client: TestClient, ready_items: Path) -> None:
    ids = {_snapshot(authed_client, c, n): c for n, c in enumerate(["correct", "incorrect"])}
    me = _reviewer(authed_client)
    for _ in range(10):
        step = authed_client.get(f"{BASE}/me", headers=me).json()["step"]
        if step["kind"] == "survey":
            authed_client.post(f"{BASE}/surveys", json=_answers(step), headers=me)
        elif step["kind"] == "trial":
            adv = step["advisory"]
            if ids[adv["id"]] == "correct":  # opens the evidence of the correct one only
                authed_client.post(
                    f"{BASE}/claims/{adv['claims'][0]['id']}/trace-opens", headers=me
                )
            authed_client.post(
                f"{BASE}/snapshots/{adv['id']}/trials",
                json={"decision": "follow", "response_ms": 2000},
                headers=me,
            )
        else:
            break
    out = authed_client.get(f"{BASE}/export").json()
    by = {t["snapshot_id"]: t for t in out["trials"]}
    correct = next(k for k, v in ids.items() if v == "correct")
    incorrect = next(k for k, v in ids.items() if v == "incorrect")
    assert by[correct]["reliance"] == "appropriate_reliance" and by[correct]["evidence_opened"] == 1
    assert by[incorrect]["reliance"] == "over_reliance" and by[incorrect]["evidence_opened"] == 0
    assert {s["timepoint"] for s in out["surveys"]} == {
        "pre_exposure",
        "post_error",
        "post_recovery",
    }
    assert all("name" not in json.dumps(t) for t in out["trials"])
    # The reviewer can't export.
    assert authed_client.get(f"{BASE}/export", headers=me).status_code == 403

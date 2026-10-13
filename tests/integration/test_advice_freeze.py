"""Freezing advice as study stimuli (ADR-019): regenerating keeps the history, a
researcher can lock the current advisory, and from then on everyone gets exactly
it — it can't be regenerated."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION
from tests.integration.test_advice_gate import FakeLLM, _use


@pytest.fixture
def sid(authed_client: TestClient) -> str:
    fid = authed_client.post("/fighters", json={"name": "Amir", "stance": "orthodox"}).json()["id"]
    return str(
        authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
            "id"
        ]
    )


def test_regenerating_keeps_every_version_and_the_history_shows_what_made_each(
    authed_client: TestClient, sid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeLLM("First take.", ["Jab more"]))
    first = authed_client.post(f"/sessions/{sid}/advice").json()
    _use(monkeypatch, FakeLLM("Second take.", ["Move more"]))
    second = authed_client.post(f"/sessions/{sid}/advice?force_regenerate=true").json()
    assert first["advice_id"] != second["advice_id"]
    hist = authed_client.get(f"/sessions/{sid}/advice/history").json()
    assert [h["output"]["summary"] for h in hist] == ["First take.", "Second take."]
    assert all(
        h["model"] and len(h["prompt_sha256"]) == 64 and len(h["input_sha256"]) == 64 for h in hist
    )
    # The cache answers with the record it came from.
    again = authed_client.post(f"/sessions/{sid}/advice").json()
    assert again["advice_id"] == second["advice_id"] and again["locked"] is False


def test_frozen_advice_is_what_everyone_gets_and_cant_be_regenerated(
    authed_client: TestClient, sid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _use(monkeypatch, FakeLLM("Keep the jab busy.", ["Double the jab"]))
    shown = authed_client.post(f"/sessions/{sid}/advice").json()
    locked = authed_client.post(f"/sessions/{sid}/advice/lock").json()
    assert locked["id"] == shown["advice_id"] and locked["locked"] is True

    llm = FakeLLM("Something else entirely.")
    _use(monkeypatch, llm)
    r = authed_client.post(f"/sessions/{sid}/advice").json()
    assert r["summary"] == "Keep the jab busy." and r["locked"] is True and llm.calls == []
    assert authed_client.post(f"/sessions/{sid}/advice?force_regenerate=true").status_code == 409
    # Locking again is harmless: still the same frozen advisory.
    assert authed_client.post(f"/sessions/{sid}/advice/lock").json()["id"] == shown["advice_id"]
    # Other payloads aren't frozen by it.
    assert authed_client.post(f"/sessions/{sid}/advice?payload_mode=cv").json()["locked"] is False


def test_only_researchers_freeze_or_read_the_history_and_only_shown_advice(
    authed_client: TestClient, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = client.post(
        "/auth/register",
        json={
            "email": "amira@alion.test",
            "password": "ValidPass123",
            "name": "Amira",
            "role": "fighter",
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    ).json()
    h = {"Authorization": f"Bearer {body['access_token']}"}
    own = client.post(
        "/sessions",
        json={"fighter_id": body["user"]["profile_id"], "source": "live_webcam"},
        headers=h,
    ).json()["id"]
    _use(monkeypatch, FakeLLM("Good pace."))
    client.post(f"/sessions/{own}/advice", headers=h)
    assert client.post(f"/sessions/{own}/advice/lock", headers=h).status_code == 403
    assert client.get(f"/sessions/{own}/advice/history", headers=h).status_code == 403


def test_nothing_to_freeze_until_advice_was_shown(
    authed_client: TestClient, sid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert authed_client.post(f"/sessions/{sid}/advice/lock").status_code == 409
    _use(monkeypatch, FakeLLM("Signs of a concussion."))  # withheld — not a stimulus
    authed_client.post(f"/sessions/{sid}/advice")
    assert authed_client.post(f"/sessions/{sid}/advice/lock").status_code == 409

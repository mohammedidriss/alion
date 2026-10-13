"""Switching the coach's AI between local and remote from the dashboard (ADR-021):
researchers and admins only, refused for a public address, and the next advice
request follows it."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION


@pytest.fixture
def fake_servers(monkeypatch: pytest.MonkeyPatch) -> None:
    """The local server has the model; the remote one is switched off."""
    from api.routes import llm

    def models(url: str, key: str) -> list[str] | None:
        return ["gemma3:4b"] if "localhost" in url else None

    async def ping(url: str, key: str, model: str) -> dict[str, Any]:
        return {"ok": "localhost" in url, "seconds": 0.4, "reply": "ready"}

    monkeypatch.setattr(llm, "installed_models", models)
    monkeypatch.setattr(llm, "ping", ping)


def test_a_researcher_sees_both_and_switches_with_no_restart(
    authed_client: TestClient,
    two_setups: Any,
    fake_servers: None,
) -> None:
    st = authed_client.get("/v2/llm").json()
    by_name = {s["name"]: s for s in st["setups"]}
    assert st["active"] == "local" and by_name["local"]["active"] is True
    assert by_name["local"]["reachable"] and by_name["local"]["model_installed"]
    assert (
        by_name["remote"]["reachable"] is False and by_name["remote"]["label"] == "Windows laptop"
    )

    st = authed_client.put("/v2/llm", json={"choice": "remote"}).json()
    assert st["active"] == "remote" and st["in_use"]["url"] == "http://192.168.68.117:11434/v1"
    assert authed_client.post("/v2/llm/test", json={"choice": "local"}).json()["ok"] is True


def test_only_researchers_and_admins_choose_the_ai(
    client: TestClient,
    admin_client: TestClient,
    two_setups: Any,
    fake_servers: None,
) -> None:
    tok = client.post(
        "/auth/register",
        json={
            "email": "coachy@alion.test",
            "password": "ValidPass123",
            "name": "Coachy",
            "role": "coach",
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    ).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get("/v2/llm", headers=h).status_code == 403
    assert client.put("/v2/llm", json={"choice": "remote"}, headers=h).status_code == 403
    assert admin_client.put("/v2/llm", json={"choice": "remote"}).status_code == 200

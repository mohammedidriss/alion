"""Researcher accounts (ADR-062): an account of its own, not a fighter's. Only an
email on the researchers list may have one; becoming one leaves the fighter
profile it was linked to — with its recordings — exactly as it was."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION
from tests.conftest import RESEARCHER_EMAIL
from tests.integration.test_access import _session, _signup

LISTED = "res@alion.test"


@pytest.fixture(autouse=True)
def _listed(monkeypatch: pytest.MonkeyPatch) -> None:
    from api.services import researchers

    monkeypatch.setattr(researchers, "emails", lambda: {RESEARCHER_EMAIL, LISTED})


def _user_id(admin: TestClient, email: str) -> str:
    return next(u["id"] for u in admin.get("/auth/admin/users").json() if u["email"] == email)


def test_a_listed_fighter_becomes_a_researcher_and_their_profile_stays(
    client: TestClient, admin_client: TestClient
) -> None:
    me = _signup(client, LISTED, "fighter")
    sid = _session(client, me)
    uid = _user_id(admin_client, LISTED)

    r = admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "researcher"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "researcher" and r.json()["profile_id"] is None
    mine = client.get("/auth/me", headers=me.headers).json()
    assert mine["role"] == "researcher" and mine["profile_id"] is None and mine["is_researcher"]

    # The fighter profile and its recordings stay where they were; nobody signs in to it.
    fighter = client.get(f"/fighters/{me.profile_id}", headers=me.headers)
    assert fighter.status_code == 200 and fighter.json()["removed_at"] is None
    assert client.get(f"/sessions/{sid}", headers=me.headers).status_code == 200
    everyone = admin_client.get("/auth/admin/everyone").json()
    account = next(p for p in everyone if p.get("user_id") == uid)
    profile = next(p for p in everyone if p["id"] == me.profile_id)
    assert account["role"] == "researcher" and account["has_account"]
    assert profile["role"] == "fighter" and not profile["has_account"]


def test_only_a_listed_email_can_be_a_researcher(
    client: TestClient, admin_client: TestClient
) -> None:
    _signup(client, "plain@alion.test", "fighter")
    uid = _user_id(admin_client, "plain@alion.test")
    r = admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "researcher"})
    assert r.status_code == 409 and "researcher" in r.json()["detail"]

    new = {"name": "New", "password": "ValidPass123", "role": "researcher"}
    r = admin_client.post("/auth/admin/users", json={**new, "email": "other@alion.test"})
    assert r.status_code == 409
    r = admin_client.post("/auth/admin/users", json={**new, "email": LISTED})
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "researcher" and r.json()["profile_id"] is None


def test_nobody_signs_up_as_a_researcher(client: TestClient) -> None:
    r = client.post(
        "/auth/register",
        json={
            "email": LISTED,
            "password": "ValidPass123",
            "name": "Res",
            "role": "researcher",
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    )
    assert r.status_code == 403


def test_the_system_administrator_is_never_made_a_researcher(admin_client: TestClient) -> None:
    admin = next(u for u in admin_client.get("/auth/admin/users").json() if u["role"] == "admin")
    r = admin_client.patch(f"/auth/admin/users/{admin['id']}", json={"role": "researcher"})
    assert r.status_code == 403


def test_back_from_researcher_gets_a_new_profile(
    client: TestClient, admin_client: TestClient
) -> None:
    me = _signup(client, LISTED, "fighter")
    uid = _user_id(admin_client, LISTED)
    admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "researcher"})
    r = admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "coach"})
    assert r.status_code == 200
    coach = r.json()["profile_id"]
    assert coach and coach != me.profile_id
    assert admin_client.get(f"/coaches/{coach}").status_code == 200

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


def _list(monkeypatch: pytest.MonkeyPatch) -> None:
    """Put LISTED on the researchers list — after its account exists, as a listed
    address can't be signed up for (ADR-064)."""
    from api.services import researchers

    monkeypatch.setattr(researchers, "emails", lambda: {RESEARCHER_EMAIL, LISTED})


def _user_id(admin: TestClient, email: str) -> str:
    return next(u["id"] for u in admin.get("/auth/admin/users").json() if u["email"] == email)


def test_a_listed_fighter_becomes_a_researcher_and_keeps_their_training(
    client: TestClient, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ADR-062 and ADR-065: the account becomes a researcher's; the fighter profile it
    had stays its own training — sessions, heart rate, wrist tabs — still linked."""
    me = _signup(client, LISTED, "fighter")
    _list(monkeypatch)
    sid = _session(client, me)
    uid = _user_id(admin_client, LISTED)

    r = admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "researcher"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "researcher" and r.json()["profile_id"] == me.profile_id
    mine = client.get("/auth/me", headers=me.headers).json()
    assert mine["role"] == "researcher" and mine["profile_id"] == me.profile_id
    assert mine["is_researcher"]

    # Their training and its recordings are where they were, and still theirs.
    fighter = client.get(f"/fighters/{me.profile_id}", headers=me.headers)
    assert fighter.status_code == 200 and fighter.json()["removed_at"] is None
    assert client.get(f"/sessions/{sid}", headers=me.headers).status_code == 200
    removal = client.get(f"/fighters/{me.profile_id}/removal", headers=me.headers).json()
    assert removal["has_account"] is True  # someone signs in to it: a coach can't delete it
    everyone = admin_client.get("/auth/admin/everyone").json()
    person = [p for p in everyone if p.get("user_id") == uid]
    assert len(person) == 1 and person[0]["id"] == me.profile_id
    assert person[0]["role"] == "researcher" and person[0]["has_account"]


def test_only_a_listed_email_can_be_a_researcher(
    client: TestClient, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _signup(client, "plain@alion.test", "fighter")
    _list(monkeypatch)
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
    client: TestClient, admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import researchers

    me = _signup(client, LISTED, "fighter")
    _list(monkeypatch)
    uid = _user_id(admin_client, LISTED)
    admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "researcher"})
    # Listed, the researcher stays one (ADR-066): taken off the list, it can change.
    assert admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "coach"}).status_code == 403
    monkeypatch.setattr(researchers, "emails", lambda: {RESEARCHER_EMAIL})
    r = admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "coach"})
    assert r.status_code == 200
    coach = r.json()["profile_id"]
    assert coach and coach != me.profile_id
    assert admin_client.get(f"/coaches/{coach}").status_code == 200


def test_a_researchers_account_is_protected(
    client: TestClient,
    authed_client: TestClient,
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR-066: nobody removes, disables or demotes a researcher's account — not the
    system administrator, not another researcher, not the account itself — nor
    deletes the training profile that would take the login with it."""
    me = _signup(client, LISTED, "fighter")
    _list(monkeypatch)
    uid = _user_id(admin_client, LISTED)
    assert (
        admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "researcher"}).status_code
        == 200
    )
    base = f"/auth/admin/users/{uid}"
    for who in (admin_client, authed_client):  # the system administrator; another researcher
        assert who.delete(base).status_code == 403
        assert who.post(f"{base}/deactivate").status_code == 403
        assert who.patch(base, json={"is_active": False}).status_code == 403
        assert who.patch(base, json={"role": "fighter"}).status_code == 403
        assert who.delete(f"/fighters/{me.profile_id}").status_code == 403
        assert who.post(f"/fighters/{me.profile_id}/remove-account").status_code == 403
    # …nor the account itself.
    assert client.delete(f"/fighters/{me.profile_id}", headers=me.headers).status_code == 403
    assert client.get("/auth/me", headers=me.headers).json()["is_active"] is True
    person = next(
        p for p in admin_client.get("/auth/admin/everyone").json() if p.get("user_id") == uid
    )
    assert person["is_protected"] is True

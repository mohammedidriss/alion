"""Account security after the review (ADR-064): research access can't be claimed
through an address, a researcher's account is changed only by a researcher, the
system administrator can't be moved, and a role change brings its own profile."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION
from tests.integration.test_access import _signup

LISTED = "res2@alion.test"


def _list(monkeypatch: pytest.MonkeyPatch, *emails: str) -> None:
    from api.services import researchers
    from tests.conftest import RESEARCHER_EMAIL

    monkeypatch.setattr(researchers, "emails", lambda: {RESEARCHER_EMAIL, *emails})


def _register(client: TestClient, email: str) -> int:
    return client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "ValidPass123",
            "name": "Someone",
            "role": "fighter",
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    ).status_code


def _second_admin(client: TestClient, admin_client: TestClient) -> dict[str, str]:
    """An administrator who isn't the system administrator (made by it)."""
    r = admin_client.post(
        "/auth/admin/users",
        json={
            "email": "admin2@alion.test",
            "password": "ValidPass123",
            "name": "A2",
            "role": "admin",
        },
    )
    assert r.status_code == 201, r.text
    tok = client.post(
        "/auth/login", data={"username": "admin2@alion.test", "password": "ValidPass123"}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _id(admin_client: TestClient, email: str) -> str:
    return next(
        u["id"] for u in admin_client.get("/auth/admin/users").json() if u["email"] == email
    )


def test_a_listed_address_cant_be_claimed(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _list(monkeypatch, LISTED)
    assert _register(client, LISTED) == 403
    assert _register(client, LISTED.upper()) == 403
    someone = _signup(client, "someone@alion.test", "fighter")
    r = client.patch("/auth/me", json={"email": LISTED}, headers=someone.headers)
    assert r.status_code == 403
    me = client.get("/auth/me", headers=someone.headers).json()
    assert me["email"] == "someone@alion.test" and not me["is_researcher"]


def test_only_a_researcher_changes_a_researchers_account(
    client: TestClient, authed_client: TestClient, admin_client: TestClient
) -> None:
    other_admin = _second_admin(client, admin_client)
    rid = _id(admin_client, "test-coach@alion.test")  # the test researcher
    base = f"/auth/admin/users/{rid}"
    assert (
        client.post(
            f"{base}/reset-password", json={"new_password": "Other1234"}, headers=other_admin
        ).status_code
        == 403
    )
    assert (
        client.patch(base, json={"email": "mine@alion.test"}, headers=other_admin).status_code
        == 403
    )
    assert client.post(f"{base}/deactivate", headers=other_admin).status_code == 403
    # Nor can an administrator take a listed address in another case for itself.
    me = _id(admin_client, "admin2@alion.test")
    r = client.patch(
        f"/auth/admin/users/{me}", json={"email": "TEST-COACH@alion.test"}, headers=other_admin
    )
    assert r.status_code == 403
    assert client.get("/auth/me", headers=other_admin).json()["is_researcher"] is False


def test_the_system_administrator_cant_be_moved_by_promoting_an_older_account(
    client: TestClient, admin_client: TestClient
) -> None:
    import datetime as dt

    from sqlmodel import Session

    older = _signup(client, "older@alion.test", "fighter")
    oid = _id(admin_client, "older@alion.test")
    # Make it older than the system administrator, as an account promoted at install is.
    from api.deps import db_session
    from api.main import app
    from store import User

    db: Session = next(app.dependency_overrides[db_session]())  # type: ignore[call-overload]
    row = db.get(User, __import__("uuid").UUID(oid))
    assert row is not None
    row.created_at = dt.datetime(2000, 1, 1)
    db.add(row)
    db.commit()
    r = admin_client.patch(f"/auth/admin/users/{oid}", json={"role": "admin"})
    assert r.status_code == 409
    assert older.profile_id  # still a fighter


def test_a_fighter_made_a_coach_gets_a_coach_profile(
    client: TestClient, admin_client: TestClient
) -> None:
    f = _signup(client, "switch@alion.test", "fighter")
    uid = _id(admin_client, "switch@alion.test")
    r = admin_client.patch(f"/auth/admin/users/{uid}", json={"role": "coach"})
    assert r.status_code == 200
    coach = r.json()["profile_id"]
    assert coach and coach != f.profile_id
    assert admin_client.get(f"/coaches/{coach}").status_code == 200

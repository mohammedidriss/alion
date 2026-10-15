"""Removing an account (ADR-048): it can't sign in, its email is free for a new
account, its coach and physician ties end, and the person's profile and records
stay — the account can be restored while nobody else has its email."""

from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.integration.test_access import _session, _signup


def _login(client: TestClient, email: str) -> int:
    r = client.post("/auth/login", data={"username": email, "password": "ValidPass123"})
    return r.status_code


def _user_id(client: TestClient, headers: dict[str, str]) -> str:
    return str(client.get("/auth/me", headers=headers).json()["id"])


def test_a_removed_account_frees_its_email_and_keeps_the_records(
    client: TestClient, admin_client: TestClient, session: Session
) -> None:
    from store import CoachAssignment, SessionRepo

    amir = _signup(client, "amir-rm@alion.test", "fighter")
    carla = _signup(client, "carla-rm@alion.test", "coach")
    client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    sid = _session(client, amir)
    uid = _user_id(client, amir.headers)

    r = admin_client.delete(f"/auth/admin/users/{uid}")
    assert r.status_code == 200, r.text
    # No signing in, and the token it had stops working.
    assert _login(client, "amir-rm@alion.test") == 401
    assert client.get("/auth/me", headers=amir.headers).status_code == 401
    # Kept: the profile and the session. Ended: the coach's tie (history kept).
    assert SessionRepo(session).get(UUID(sid)) is not None
    (tie,) = session.exec(select(CoachAssignment)).all()
    assert tie.ended_on is not None
    person = next(p for p in admin_client.get("/auth/admin/everyone").json() if p["user_id"] == uid)
    assert person["removed"] is True and person["email"] == "amir-rm@alion.test"
    assert person["id"] == amir.profile_id

    # The email is free: a new account, with a profile of its own.
    again = _signup(client, "amir-rm@alion.test", "fighter")
    assert again.profile_id != amir.profile_id and _login(client, "amir-rm@alion.test") == 200
    # The old account can't take the email back, nor be changed until it's restored.
    assert admin_client.post(f"/auth/admin/users/{uid}/restore").status_code == 409
    assert admin_client.post(f"/auth/admin/users/{uid}/activate").status_code == 409
    assert admin_client.delete(f"/auth/admin/users/{uid}").status_code == 409


def test_a_removed_account_can_be_restored(client: TestClient, admin_client: TestClient) -> None:
    bea = _signup(client, "bea-rm@alion.test", "fighter")
    uid = _user_id(client, bea.headers)
    admin_client.delete(f"/auth/admin/users/{uid}")
    assert _login(client, "bea-rm@alion.test") == 401

    r = admin_client.post(f"/auth/admin/users/{uid}/restore")
    assert r.status_code == 200, r.text
    assert _login(client, "bea-rm@alion.test") == 200
    person = next(p for p in admin_client.get("/auth/admin/everyone").json() if p["user_id"] == uid)
    assert person["removed"] is False and person["id"] == bea.profile_id


def test_who_can_remove_whom(admin_client: TestClient, authed_client: TestClient) -> None:
    admin_id = str(admin_client.get("/auth/me").json()["id"])
    researcher_id = str(authed_client.get("/auth/me").json()["id"])
    assert admin_client.delete(f"/auth/admin/users/{admin_id}").status_code == 400  # not yourself
    # An admin can't remove the researcher; the researcher can remove an admin —
    # but never the system administrator, the founding admin account.
    assert admin_client.delete(f"/auth/admin/users/{researcher_id}").status_code == 403
    assert authed_client.delete(f"/auth/admin/users/{admin_id}").status_code == 403
    later = admin_client.post(
        "/auth/admin/users",
        json={
            "email": "later-admin@alion.test",
            "password": "Another-Pass-123!",
            "name": "Later Admin",
            "role": "admin",
        },
    ).json()["id"]
    assert authed_client.delete(f"/auth/admin/users/{later}").status_code == 200

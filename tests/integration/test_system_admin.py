"""The system administrator — the founding admin account — can't be removed,
disabled or demoted by anyone, so the system always keeps its administrator.
Admin accounts added later can still be managed."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from store import User, UserRole


def _system_admin(session: Session) -> User:
    user = session.exec(select(User).where(User.email == "test-admin@alion.test")).first()
    assert user is not None
    return user


def test_another_administrator_cant_remove_disable_or_demote_it(
    admin_client: TestClient, authed_client: TestClient, session: Session
) -> None:
    # authed_client is a researcher: every administrator power (ADR-046).
    sid = _system_admin(session).id
    r = authed_client.delete(f"/auth/admin/users/{sid}")
    assert r.status_code == 403 and "system administrator" in r.json()["detail"]
    assert authed_client.post(f"/auth/admin/users/{sid}/deactivate").status_code == 403
    assert (
        authed_client.patch(f"/auth/admin/users/{sid}", json={"is_active": False}).status_code
        == 403
    )
    r = authed_client.patch(f"/auth/admin/users/{sid}", json={"role": "coach"})
    assert r.status_code == 403  # demote-then-remove would get around the rest

    session.expire_all()
    admin = _system_admin(session)
    assert admin.is_active and admin.removed_at is None and admin.role == UserRole.ADMIN
    # It still signs in and works.
    assert admin_client.get("/auth/admin/users").status_code == 200


def test_it_cant_disable_or_demote_itself_either(
    admin_client: TestClient, session: Session
) -> None:
    sid = _system_admin(session).id
    assert (
        admin_client.patch(f"/auth/admin/users/{sid}", json={"is_active": False}).status_code == 403
    )
    assert (
        admin_client.patch(f"/auth/admin/users/{sid}", json={"role": "fighter"}).status_code == 403
    )
    assert admin_client.delete(f"/auth/admin/users/{sid}").status_code == 400  # own account


def test_its_other_details_can_still_be_edited(
    admin_client: TestClient, authed_client: TestClient, session: Session
) -> None:
    sid = _system_admin(session).id
    r = authed_client.patch(f"/auth/admin/users/{sid}", json={"name": "Head Admin"})
    assert r.status_code == 200 and r.json()["name"] == "Head Admin"


def test_an_admin_added_later_can_be_managed(admin_client: TestClient, session: Session) -> None:
    r = admin_client.post(
        "/auth/admin/users",
        json={
            "email": "second-admin@alion.test",
            "password": "Another-Pass-123!",
            "name": "Second Admin",
            "role": "admin",
        },
    )
    assert r.status_code == 201, r.text
    second = r.json()["id"]
    assert admin_client.post(f"/auth/admin/users/{second}/deactivate").status_code == 200
    assert admin_client.delete(f"/auth/admin/users/{second}").status_code == 200


def test_the_people_list_marks_only_the_system_administrator(
    admin_client: TestClient, session: Session
) -> None:
    admin_client.post(
        "/auth/admin/users",
        json={
            "email": "second-admin@alion.test",
            "password": "Another-Pass-123!",
            "name": "Second Admin",
            "role": "admin",
        },
    )
    people = admin_client.get("/auth/admin/everyone").json()
    protected = [p["email"] for p in people if p["is_system_admin"]]
    assert protected == ["test-admin@alion.test"]


def test_nobody_else_can_reset_its_password_or_change_its_email(
    admin_client: TestClient, authed_client: TestClient, session: Session
) -> None:
    sid = _system_admin(session).id
    r = authed_client.post(
        f"/auth/admin/users/{sid}/reset-password", json={"new_password": "Taken-Over-123!"}
    )
    assert r.status_code == 403
    r = authed_client.patch(f"/auth/admin/users/{sid}", json={"email": "someone-else@alion.test"})
    assert r.status_code == 403
    session.expire_all()
    assert _system_admin(session).email == "test-admin@alion.test"
    # The system administrator itself still can.
    r = admin_client.post(
        f"/auth/admin/users/{sid}/reset-password", json={"new_password": "My-Own-New-123!"}
    )
    assert r.status_code == 200
    r = admin_client.patch(f"/auth/admin/users/{sid}", json={"email": "head-admin@alion.test"})
    assert r.status_code == 200 and r.json()["email"] == "head-admin@alion.test"

"""A fighter confirms joining a gym (ADR-035): a gym that adds a fighter by System
ID invites them, and its managers see nothing of their training until they accept."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION
from tests.integration.test_access import Account, _session, _signup


def _manager(client: TestClient, email: str, gym_name: str) -> tuple[dict[str, str], str]:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "ValidPass123",
            "name": "Gina",
            "role": "gym_manager",
            "gym_name": gym_name,
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return headers, client.get("/gym-managers/me", headers=headers).json()["gym_id"]


def _import(client: TestClient, gym: str, who: Account, headers: dict[str, str]):  # type: ignore[no-untyped-def]
    return client.post(
        f"/gyms/{gym}/members/import", json={"system_id": who.profile_id}, headers=headers
    )


def test_an_imported_fighter_is_invited_and_the_gym_sees_nothing_until_they_accept(
    client: TestClient,
) -> None:
    gina, gym = _manager(client, "gina-i@alion.test", "Northside")
    amir = _signup(client, "amir-i@alion.test", "fighter")
    sid = _session(client, amir)

    r = _import(client, gym, amir, gina)
    assert r.status_code == 201 and r.json()["status"] == "invited", r.text
    assert r.json()["status_note"] == "Invited by Gina"
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403
    assert amir.profile_id not in {f["id"] for f in client.get("/fighters", headers=gina).json()}
    # Asking twice, or the gym switching it on itself, is refused.
    assert _import(client, gym, amir, gina).status_code == 409
    mid = r.json()["id"]
    flip = client.patch(
        f"/gyms/{gym}/members/{mid}/status", json={"status": "active"}, headers=gina
    )
    assert flip.status_code == 409
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403

    # Amir sees the invitation — who'll see his data — and accepts.
    invites = client.get("/v2/gym-invitations", headers=amir.headers).json()
    assert [(i["gym_name"], i["managers"], i["invited_by"]) for i in invites] == [
        ("Northside", ["Gina"], "Gina")
    ]
    assert client.post(
        f"/v2/gym-invitations/{invites[0]['id']}/accept", headers=amir.headers
    ).json() == {"status": "active"}
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 200
    assert client.get("/v2/gym-invitations", headers=amir.headers).json() == []
    assert client.get("/v2/privacy/me", headers=amir.headers).json()["viewers"]["gyms"] == [
        "Northside"
    ]
    assert _import(client, gym, amir, gina).status_code == 409  # already a member


def test_a_fighter_can_decline_and_be_asked_again(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-d@alion.test", "Eastside")
    bea = _signup(client, "bea-d@alion.test", "fighter")
    sid = _session(client, bea)
    mid = _import(client, gym, bea, gina).json()["id"]

    assert client.post(f"/v2/gym-invitations/{mid}/decline", headers=bea.headers).status_code == 200
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403
    members = {m["id"]: m for m in client.get(f"/gyms/{gym}/members", headers=gina).json()}
    assert members[mid]["status"] == "declined"
    # Declined can't be switched on by the gym; it can only ask again.
    flip = client.patch(f"/gyms/{gym}/members/{mid}/status", json={"status": "trial"}, headers=gina)
    assert flip.status_code == 409
    again = _import(client, gym, bea, gina)
    assert (
        again.status_code == 201
        and again.json()["id"] == mid
        and again.json()["status"] == "invited"
    )


def test_only_the_invited_fighter_answers(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-o@alion.test", "Westside")
    amir = _signup(client, "amir-o@alion.test", "fighter")
    bea = _signup(client, "bea-o@alion.test", "fighter")
    mid = _import(client, gym, amir, gina).json()["id"]
    assert client.post(f"/v2/gym-invitations/{mid}/accept", headers=bea.headers).status_code == 404
    assert client.post(f"/v2/gym-invitations/{mid}/accept", headers=gina).status_code == 404
    assert client.get("/v2/gym-invitations", headers=gina).json() == []


def test_a_fighter_who_left_comes_back_only_by_accepting(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-l@alion.test", "Southside")
    amir = _signup(client, "amir-l@alion.test", "fighter")
    sid = _session(client, amir)
    mid = _import(client, gym, amir, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 200

    assert client.delete(f"/gyms/{gym}/members/{mid}", headers=gina).status_code == 204
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403
    back = client.patch(
        f"/gyms/{gym}/members/{mid}/status", json={"status": "active"}, headers=gina
    )
    assert back.status_code == 409
    assert _import(client, gym, amir, gina).json()["status"] == "invited"
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 200


def test_coaches_and_accounts_the_gym_makes_join_at_once(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-c@alion.test", "Midtown")
    carla = _signup(client, "carla-c@alion.test", "coach")
    r = _import(client, gym, carla, gina)
    assert r.status_code == 201 and r.json()["status"] == "active"
    r = client.post(
        f"/gyms/{gym}/members/create-account",
        json={
            "name": "Nova",
            "email": "nova-c@alion.test",
            "password": "ValidPass123",
            "role": "fighter",
        },
        headers=gina,
    )
    assert r.status_code == 201 and r.json()["status"] == "active"

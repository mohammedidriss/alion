"""A gym's staff (ADR-052): roles at a gym — owner, manager, head coach, coach —
invited and accepted; access worked out from them; support-team links made
through a gym only with its own coaching staff."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_access import Account, _session, _signup
from tests.integration.test_gym_invitations import _import, _manager


def _invite(client: TestClient, gym: str, by: dict[str, str], who: Account | str, role: str):  # type: ignore[no-untyped-def]
    body = {"email": who, "role": role} if isinstance(who, str) else {"role": role}
    if not isinstance(who, str):
        body["system_id"] = str(who.profile_id)
    return client.post(f"/gyms/{gym}/staff", json=body, headers=by)


def _accept(client: TestClient, who: Account, staff_id: int) -> None:
    r = client.post(f"/v2/my-staff/{staff_id}/accept", headers=who.headers)
    assert r.status_code == 200, r.text


def test_the_founder_owns_the_gym_and_invites_staff_who_accept(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-s@alion.test", "Harbour")
    me = client.get("/auth/me", headers=gina).json()
    assert me["gym_roles"] == [{"gym_id": gym, "gym_name": "Harbour", "role": "owner"}]
    (owner,) = client.get(f"/gyms/{gym}/staff", headers=gina).json()
    assert owner["role"] == "owner" and owner["status"] == "active"

    carla = _signup(client, "carla-s@alion.test", "coach")
    r = _invite(client, gym, gina, "carla-s@alion.test", "coach")
    assert r.status_code == 201 and r.json()["status"] == "invited", r.text
    assert _invite(client, gym, gina, "carla-s@alion.test", "coach").status_code == 409
    # Invited, she sees the gym's members only once she accepts.
    assert client.get(f"/gyms/{gym}/members", headers=carla.headers).status_code == 403
    (inv,) = client.get("/v2/my-staff", headers=carla.headers).json()
    assert inv["gym_name"] == "Harbour" and inv["invited_by_name"] == "Gina"
    _accept(client, carla, inv["id"])
    assert client.get(f"/gyms/{gym}/members", headers=carla.headers).status_code == 200
    roles = client.get("/auth/me", headers=carla.headers).json()["gym_roles"]
    assert roles == [{"gym_id": gym, "gym_name": "Harbour", "role": "coach"}]
    # A fighter account can't be a coach; only an owner adds an owner.
    _signup(client, "amir-s@alion.test", "fighter")
    assert _invite(client, gym, gina, "amir-s@alion.test", "coach").status_code == 422


def test_a_coach_can_manage_a_gym_and_head_coaches_see_its_fighters(
    client: TestClient,
) -> None:
    gina, gym = _manager(client, "gina-h@alion.test", "Northgate")
    amir = _signup(client, "amir-h@alion.test", "fighter")
    sid = _session(client, amir)
    mid = _import(client, gym, amir, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)

    # A coach account as the gym's manager: the gym's pages work for her.
    mona = _signup(client, "mona-h@alion.test", "coach")
    _accept(client, mona, _invite(client, gym, gina, "mona-h@alion.test", "manager").json()["id"])
    assert client.get("/gym-managers/me", headers=mona.headers).json()["gym_id"] == gym
    assert client.get(f"/sessions/{sid}", headers=mona.headers).status_code == 200
    assert _invite(client, gym, mona.headers, "x@alion.test", "owner").status_code == 403

    # A head coach sees the gym's fighters' training but doesn't manage its staff.
    hugo = _signup(client, "hugo-h@alion.test", "coach")
    _accept(client, hugo, _invite(client, gym, gina, hugo, "head_coach").json()["id"])
    assert client.get(f"/sessions/{sid}", headers=hugo.headers).status_code == 200
    assert _invite(client, gym, hugo.headers, "mona-h@alion.test", "coach").status_code == 403
    leaders = client.get("/v2/privacy/me", headers=amir.headers).json()["viewers"]["gym_managers"]
    assert set(leaders) >= {"Gina", "Mona-H", "Hugo-H"}


def test_a_gym_assigns_only_its_own_coaches_and_keeps_an_owner(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-o@alion.test", "Southbank")
    amir = _signup(client, "amir-o@alion.test", "fighter")
    dana = _signup(client, "dana-o@alion.test", "coach")  # not on the gym's staff
    mid = _import(client, gym, amir, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    url = f"/fighters/{amir.profile_id}/coach-assignments"
    body = {"coach_id": dana.profile_id, "role": "nutrition"}
    assert client.post(url, json=body, headers=gina).status_code == 422  # through the gym: no
    r = client.post(url, json=body, headers=amir.headers)  # Amir's own: yes
    assert r.status_code == 201 and r.json()["source_gym_id"] is None

    carla = _signup(client, "carla-o@alion.test", "coach")
    _accept(client, carla, _invite(client, gym, gina, carla, "coach").json()["id"])
    r = client.post(url, json={"coach_id": carla.profile_id, "role": "physio"}, headers=gina)
    assert r.status_code == 201 and r.json()["source_gym_name"] == "Southbank"

    # The last owner stays.
    (own,) = [
        s for s in client.get(f"/gyms/{gym}/staff", headers=gina).json() if s["role"] == "owner"
    ]
    assert client.post(f"/v2/my-staff/{own['id']}/leave", headers=gina).status_code == 409

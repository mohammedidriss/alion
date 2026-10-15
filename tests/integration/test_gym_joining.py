"""Joining a gym, step 4 of the gym workflow (ADR-055): a fighter asks to join with
the gym's code and the gym approves — on trial, then active; joining means
accepting the gym's rules (again when they change) and gives an emergency
contact; a fight camp names its bout; squads show who checked in."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_access import _session, _signup
from tests.integration.test_gym_invitations import _import, _manager

CONTACT = {
    "emergency_contact_name": "Sara",
    "emergency_contact_phone": "+966 5 0000 0000",
    "emergency_contact_relation": "sister",
}


def test_a_fighter_asks_with_the_code_and_the_gym_approves(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-j@alion.test", "Joinville")
    amir = _signup(client, "amir-j@alion.test", "fighter")
    carla = _signup(client, "carla-j@alion.test", "coach")
    sid = _session(client, amir)
    assert client.post(f"/gyms/{gym}/join-code", headers=carla.headers).status_code == 403
    code = client.post(f"/gyms/{gym}/join-code", headers=gina).json()["join_code"]
    assert len(code) == 8

    preview = client.get(f"/v2/join/{code.lower()}", headers=amir.headers).json()
    assert preview["gym_name"] == "Joinville" and "Gina" in preview["leaders"]
    r = client.post(f"/v2/join/{code}", json=CONTACT, headers=amir.headers)
    assert r.status_code == 200 and r.json()["status"] == "applied", r.text
    assert client.post(f"/v2/join/{code}", json={}, headers=amir.headers).status_code == 409
    # Asked, not in: the gym sees nothing, can't check them in, and approves explicitly.
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403
    (req,) = [
        m
        for m in client.get(f"/gyms/{gym}/members", headers=gina).json()
        if m["status"] == "applied"
    ]
    assert req["has_emergency_contact"] is True
    url = f"/gyms/{gym}/members/{req['id']}"
    assert client.patch(f"{url}/status", json={"status": "active"}, headers=gina).status_code == 409
    assert (
        client.post(
            f"/gyms/{gym}/checkins",
            json={"member_id": amir.profile_id, "member_type": "fighter"},
            headers=gina,
        ).status_code
        == 409
    )

    r = client.post(f"{url}/approve", json={"status": "trial"}, headers=gina)
    assert r.status_code == 200 and r.json()["status"] == "trial", r.text
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 200
    assert (
        client.patch(f"{url}/status", json={"status": "active"}, headers=gina).json()["status"]
        == "active"
    )
    me = client.get(f"/fighters/{amir.profile_id}", headers=amir.headers).json()
    assert me["emergency_contact_name"] == "Sara" and me["gym_id"] == gym
    kept = [
        h["what"] for h in client.get("/v2/privacy/me", headers=amir.headers).json()["holdings"]
    ]
    assert "Your emergency contact (name, phone)" in kept

    # A new code retires the old one; stopping it retires both.
    new = client.post(f"/gyms/{gym}/join-code", headers=gina).json()["join_code"]
    assert client.get(f"/v2/join/{code}", headers=amir.headers).status_code == 404
    client.delete(f"/gyms/{gym}/join-code", headers=gina)
    assert client.get(f"/v2/join/{new}", headers=amir.headers).status_code == 404


def test_a_request_can_be_rejected_or_withdrawn(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-r@alion.test", "Rejecton")
    amir = _signup(client, "amir-r@alion.test", "fighter")
    bea = _signup(client, "bea-r@alion.test", "fighter")
    code = client.post(f"/gyms/{gym}/join-code", headers=gina).json()["join_code"]
    for f in (amir, bea):
        client.post(f"/v2/join/{code}", json={}, headers=f.headers)
    reqs = {
        m["member_name"]: m["id"] for m in client.get(f"/gyms/{gym}/members", headers=gina).json()
    }
    assert (
        client.post(f"/gyms/{gym}/members/{reqs['Amir-R']}/reject", headers=gina).json()["status"]
        == "declined"
    )
    (bea_req,) = client.get("/v2/my-gyms", headers=bea.headers).json()
    assert bea_req["status"] == "applied"
    assert client.post(f"/v2/my-gyms/{bea_req['id']}/leave", headers=bea.headers).status_code == 200
    assert client.get("/v2/my-gyms", headers=bea.headers).json() == []
    # The gym can't invite someone waiting for its answer.
    client.post(f"/v2/join/{code}", json={}, headers=bea.headers)
    assert _import(client, gym, bea, gina).status_code == 409


def test_joining_means_accepting_the_rules_again_when_they_change(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-u@alion.test", "Rulesville")
    amir = _signup(client, "amir-u@alion.test", "fighter")
    r = client.patch(f"/gyms/{gym}", json={"rules": "Gloves on in the ring."}, headers=gina)
    assert r.json()["rules_version"] == 1
    mid = _import(client, gym, amir, gina).json()["id"]
    (inv,) = client.get("/v2/gym-invitations", headers=amir.headers).json()
    assert inv["rules"] == "Gloves on in the ring."
    accept = f"/v2/gym-invitations/{mid}/accept"
    assert client.post(accept, headers=amir.headers).status_code == 422
    assert client.post(accept, json={"accept_rules": True}, headers=amir.headers).status_code == 200
    (mine,) = client.get("/v2/my-gyms", headers=amir.headers).json()
    assert mine["rules_pending"] is False

    client.patch(f"/gyms/{gym}", json={"rules": "Gloves on. Wraps too."}, headers=gina)
    (mine,) = client.get("/v2/my-gyms", headers=amir.headers).json()
    assert mine["rules_pending"] is True
    member = next(
        m
        for m in client.get(f"/gyms/{gym}/members", headers=gina).json()
        if m["member_name"] == "Amir-U"
    )
    assert member["rules_current"] is False
    client.post(f"/v2/my-gyms/{mine['id']}/accept-rules", headers=amir.headers)
    assert client.get("/v2/my-gyms", headers=amir.headers).json()[0]["rules_pending"] is False


def test_a_camp_ends_with_its_bout_and_squads_show_check_ins(
    client: TestClient, authed_client: TestClient
) -> None:
    gina, gym = _manager(client, "gina-k2@alion.test", "Campton")
    amir = _signup(client, "amir-k2@alion.test", "fighter")
    mid = _import(client, gym, amir, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    bout = authed_client.post("/bouts", json={"label": "Riyadh card"}).json()
    r = client.post(
        f"/gyms/{gym}/squads",
        json={"name": "October camp", "kind": "camp", "bout_id": bout["id"]},
        headers=gina,
    )
    assert r.status_code == 201, r.text
    camp = r.json()
    assert camp["ends_on"] == bout["scheduled_at"][:10] and camp["bout_label"].startswith(
        "Riyadh card"
    )
    client.post(f"/squads/{camp['id']}/members", json={"fighter_id": amir.profile_id}, headers=gina)
    client.post(
        f"/gyms/{gym}/checkins",
        json={"member_id": amir.profile_id, "member_type": "fighter"},
        headers=gina,
    )
    (week,) = client.get(f"/gyms/{gym}/squads", headers=gina).json()
    assert week["checked_in_7d"] == 1

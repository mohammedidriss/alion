"""Roles and permissions (ADR-046): the researcher sees and does everything, with
health-note reads logged; physicians see what the fighters who chose them share;
coaches see health notes only when the fighter shares them."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_access import _session, _signup


def test_the_researcher_sees_every_fighter_and_has_admin_powers(
    client: TestClient, authed_client: TestClient
) -> None:
    amir = _signup(client, "amir-rs@alion.test", "fighter")
    sid = _session(client, amir)
    client.patch(
        f"/fighters/{amir.profile_id}/medical", json={"blood_type": "B+"}, headers=amir.headers
    )

    # authed_client is a researcher with no tie to Amir.
    assert authed_client.get(f"/sessions/{sid}").status_code == 200
    assert authed_client.get(f"/fighters/{amir.profile_id}/medical").json()["blood_type"] == "B+"
    assert amir.profile_id in {f["id"] for f in authed_client.get("/fighters").json()}
    log = client.get(f"/fighters/{amir.profile_id}/medical/access-log", headers=amir.headers).json()
    assert any(e["role"] == "coach" and e["allowed"] for e in log)  # the researcher's read, logged
    # Administrator powers: the account list.
    assert authed_client.get("/auth/admin/users").status_code == 200
    me = authed_client.get("/auth/me").json()
    assert me["is_researcher"] is True


def test_a_physician_sees_what_the_fighter_who_chose_them_shares(client: TestClient) -> None:
    amir = _signup(client, "amir-ph@alion.test", "fighter")
    bea = _signup(client, "bea-ph@alion.test", "fighter")
    doc = _signup(client, "doc-ph@alion.test", "physician")
    sid = _session(client, amir)
    client.patch(
        f"/fighters/{amir.profile_id}/medical", json={"blood_type": "A-"}, headers=amir.headers
    )
    med = f"/fighters/{amir.profile_id}/medical"

    assert client.get(med, headers=doc.headers).status_code == 403  # not chosen yet
    assert client.get("/physicians/me/fighters", headers=doc.headers).json() == []
    # Only Amir chooses his physician; only physician accounts can be chosen.
    assert (
        client.post(
            f"/fighters/{amir.profile_id}/physicians",
            json={"email": "doc-ph@alion.test"},
            headers=bea.headers,
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/fighters/{amir.profile_id}/physicians",
            json={"email": "bea-ph@alion.test"},
            headers=amir.headers,
        ).status_code
        == 404
    )
    r = client.post(
        f"/fighters/{amir.profile_id}/physicians",
        json={"email": "DOC-ph@alion.test"},
        headers=amir.headers,
    )
    assert r.status_code == 201, r.text

    assert client.get(med, headers=doc.headers).json()["blood_type"] == "A-"
    assert client.get(f"/sessions/{sid}", headers=doc.headers).status_code == 200  # training, read
    assert (
        client.put(f"/sessions/{sid}/labels", json=[], headers=doc.headers).status_code == 403
    )  # no changes
    assert [
        f["name"] for f in client.get("/physicians/me/fighters", headers=doc.headers).json()
    ] == ["Amir-Ph"]
    assert client.get(f"/fighters/{bea.profile_id}/medical", headers=doc.headers).status_code == 403

    # Removed: no access, the history kept.
    assert (
        client.delete(
            f"/fighters/{amir.profile_id}/physicians/{r.json()['id']}", headers=amir.headers
        ).status_code
        == 204
    )
    assert client.get(med, headers=doc.headers).status_code == 403
    me = client.get("/v2/privacy/me", headers=amir.headers).json()
    assert me["viewers"]["physicians"] == []


def test_only_the_fighter_shares_health_notes_with_a_coach(client: TestClient) -> None:
    amir = _signup(client, "amir-hs@alion.test", "fighter")
    carla = _signup(client, "carla-hs@alion.test", "coach")
    r = client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach", "health_access": True},
        headers=amir.headers,
    )
    assert r.json()["health_access"] is True  # Amir chose it
    aid = r.json()["id"]
    # Carla can't grant herself access, Amir can take it back.
    url = f"/fighters/{amir.profile_id}/coach-assignments/{aid}"
    assert client.patch(url, json={"health_access": True}, headers=carla.headers).status_code == 403
    assert client.patch(url, json={"health_access": False}, headers=amir.headers).json() == {
        "health_access": False
    }
    assert (
        client.get(f"/fighters/{amir.profile_id}/medical", headers=carla.headers).status_code == 403
    )
    me = client.get("/v2/privacy/me", headers=amir.headers).json()
    assert me["viewers"]["coaches_with_health"] == [] and len(me["viewers"]["coaches"]) == 1


def test_the_account_says_which_studies_it_takes_part_in(
    client: TestClient, authed_client: TestClient
) -> None:
    carla = _signup(client, "carla-st@alion.test", "coach")
    me = client.get("/auth/me", headers=carla.headers).json()
    assert me["is_rq1_rater"] is False and me["is_reviewer"] is False
    authed_client.post("/studies/rq1/raters", json={"email": "carla-st@alion.test"})
    assert client.get("/auth/me", headers=carla.headers).json()["is_rq1_rater"] is True

"""Record-level access control (ADR-017): who may see or change which fighter's
data — the fighter, their coaches, their gym's managers, researchers, admins —
checked by the API on every route, not just hidden in the dashboard."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION


@dataclass
class Account:
    headers: dict[str, str]
    profile_id: str | None


def _signup(client: TestClient, email: str, role: str) -> Account:
    r = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "ValidPass123",
            "name": email.split("@")[0].title(),
            "role": role,
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    return Account({"Authorization": f"Bearer {body['access_token']}"}, body["user"]["profile_id"])


def _session(client: TestClient, who: Account) -> str:
    r = client.post(
        "/sessions",
        json={"fighter_id": who.profile_id, "source": "live_webcam"},
        headers=who.headers,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


@pytest.fixture
def people(client: TestClient) -> dict[str, Account]:
    return {
        "amir": _signup(client, "amir@alion.test", "fighter"),
        "bea": _signup(client, "bea@alion.test", "fighter"),
        "coach": _signup(client, "carla@alion.test", "coach"),
    }


def test_a_fighter_sees_their_own_data_and_nobody_elses(
    client: TestClient, people: dict[str, Account]
) -> None:
    amir, bea = people["amir"], people["bea"]
    sid = _session(client, amir)

    assert client.get(f"/sessions/{sid}", headers=amir.headers).status_code == 200
    assert client.get(f"/sessions/{sid}", headers=bea.headers).status_code == 403
    assert client.get(f"/sessions/{sid}/events", headers=bea.headers).status_code == 403
    assert client.delete(f"/sessions/{sid}", headers=bea.headers).status_code == 403
    assert sid not in {s["id"] for s in client.get("/sessions", headers=bea.headers).json()}
    # …nor open a session for someone else.
    r = client.post(
        "/sessions",
        json={"fighter_id": amir.profile_id, "source": "live_webcam"},
        headers=bea.headers,
    )
    assert r.status_code == 403
    # The fighter list shows a fighter only themselves.
    assert [f["id"] for f in client.get("/fighters", headers=bea.headers).json()] == [
        bea.profile_id
    ]


def test_medical_records_are_the_fighter_and_their_coaches_only_and_every_access_is_logged(
    client: TestClient, people: dict[str, Account]
) -> None:
    amir, bea, coach = people["amir"], people["bea"], people["coach"]
    url = f"/fighters/{amir.profile_id}/medical"
    assert client.patch(url, json={"blood_type": "O+"}, headers=amir.headers).status_code == 200
    assert client.get(url, headers=bea.headers).status_code == 403
    assert client.get(url, headers=coach.headers).status_code == 403  # not Amir's coach yet

    # Amir makes Carla his coach — now she can.
    r = client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": coach.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    assert r.status_code in (200, 201), r.text
    assert client.get(url, headers=coach.headers).json()["blood_type"] == "O+"

    log = client.get(f"{url}/access-log", headers=amir.headers).json()
    seen = {(e["role"], e["action"], e["allowed"]) for e in log}
    assert ("fighter", "write", True) in seen
    assert ("fighter", "read", False) in seen  # Bea, refused
    assert ("coach", "read", False) in seen and ("coach", "read", True) in seen
    assert all("blood" not in str(e) for e in log)  # never the content


def test_a_coach_sees_only_their_fighters_and_cant_appoint_themselves(
    client: TestClient, people: dict[str, Account]
) -> None:
    amir, bea, coach = people["amir"], people["bea"], people["coach"]
    sid = _session(client, bea)
    assert client.get(f"/sessions/{sid}", headers=coach.headers).status_code == 403
    r = client.post(
        f"/fighters/{bea.profile_id}/coach-assignments",
        json={"coach_id": coach.profile_id, "role": "head_coach"},
        headers=coach.headers,
    )
    assert r.status_code == 403  # a coach can't make themselves anyone's coach
    # A fighter a coach adds is theirs.
    r = client.post("/fighters", json={"name": "Dina", "stance": "orthodox"}, headers=coach.headers)
    assert r.status_code == 201
    dina = r.json()["id"]
    r = client.post(
        "/sessions", json={"fighter_id": dina, "source": "live_webcam"}, headers=coach.headers
    )
    assert r.status_code == 201
    assert amir.profile_id not in {
        f["id"] for f in client.get("/fighters", headers=coach.headers).json()
    }


def test_gym_managers_see_their_gyms_training_but_never_medical(
    client: TestClient, admin_client: TestClient, people: dict[str, Account]
) -> None:
    amir, bea = people["amir"], people["bea"]
    gym = admin_client.post("/gyms", json={"name": "Northside"}).json()["id"]
    r = admin_client.post(
        "/auth/admin/users",
        json={
            "email": "gina@alion.test",
            "password": "ValidPass123",
            "name": "Gina",
            "role": "gym_manager",
            "gym_id": gym,
        },
    )
    assert r.status_code == 201, r.text
    tok = client.post(
        "/auth/login", data={"username": "gina@alion.test", "password": "ValidPass123"}
    ).json()["access_token"]
    gina = {"Authorization": f"Bearer {tok}"}
    assert (
        client.post("/auth/terms/accept", json={"version": TERMS_VERSION}, headers=gina).status_code
        == 200
    )
    r = client.post(
        f"/gyms/{gym}/members",
        json={"member_id": amir.profile_id, "member_type": "fighter"},
        headers=gina,
    )
    assert r.status_code in (200, 201), r.text

    amir_sid, bea_sid = _session(client, amir), _session(client, bea)
    assert client.get(f"/sessions/{amir_sid}", headers=gina).status_code == 200
    assert client.get(f"/sessions/{bea_sid}", headers=gina).status_code == 403  # not her gym
    assert client.get(f"/fighters/{amir.profile_id}/medical", headers=gina).status_code == 403
    # Sees, doesn't change: writing labels on the session is refused.
    r = client.put(f"/sessions/{amir_sid}/labels", json=[], headers=gina)
    assert r.status_code == 403


def test_admins_manage_accounts_and_profiles_but_never_see_training_or_medical(
    client: TestClient, admin_client: TestClient, people: dict[str, Account]
) -> None:
    amir = people["amir"]
    sid = _session(client, amir)
    assert admin_client.get(f"/fighters/{amir.profile_id}").status_code == 200
    assert admin_client.get(f"/sessions/{sid}").status_code == 403
    assert admin_client.get(f"/fighters/{amir.profile_id}/medical").status_code == 403
    assert admin_client.get(f"/fighters/{amir.profile_id}/readiness").status_code == 403


def test_research_datasets_are_for_researchers_only(
    client: TestClient, authed_client: TestClient, people: dict[str, Account]
) -> None:
    assert authed_client.get("/v2/datasets").status_code == 200  # the researcher
    did = authed_client.post("/v2/datasets", json={"name": "RQ2"}).json()["id"]
    for who in people.values():
        assert client.get("/v2/datasets", headers=who.headers).status_code == 403
        assert client.post(f"/v2/datasets/{did}/export", headers=who.headers).status_code == 403
    assert client.get("/auth/me", headers=people["coach"].headers).json()["is_researcher"] is False
    assert authed_client.get("/auth/me").json()["is_researcher"] is True


def test_nobody_signs_up_as_admin_or_gym_manager(client: TestClient) -> None:
    for role in ("admin", "gym_manager"):
        r = client.post(
            "/auth/register",
            json={
                "email": f"x-{role}@alion.test",
                "password": "ValidPass123",
                "name": "X",
                "role": role,
                "accept_terms": True,
                "terms_version": TERMS_VERSION,
            },
        )
        assert r.status_code == 403


def test_referees_need_a_sign_in_and_only_admins_add_them(
    client: TestClient, admin_client: TestClient, people: dict[str, Account]
) -> None:
    assert client.get("/referees").status_code == 401
    assert client.post("/referees", json={"name": "Ref"}).status_code == 401
    r = client.post("/referees", json={"name": "Ref"}, headers=people["coach"].headers)
    assert r.status_code == 403
    assert admin_client.post("/referees", json={"name": "Ref"}).status_code == 201


def test_a_file_name_cant_reach_outside_its_folder(
    client: TestClient, people: dict[str, Account]
) -> None:
    amir = people["amir"]
    sid = _session(client, amir)
    r = client.post(
        f"/sessions/{sid}/attachments",
        files={"file": ("../../../escape.txt", b"hello", "text/plain")},
        headers=amir.headers,
    )
    assert r.status_code in (200, 201), r.text
    assert r.json()["filename"] == "escape.txt" and ".." not in r.json()["path"]

    from api.services import dataset_store

    with pytest.raises(ValueError):
        dataset_store.safe_device_id("../../evil")
    assert dataset_store.safe_device_id("a1b2-c3_d4") == "a1b2-c3_d4"


def test_deleting_someone_elses_weigh_in_through_your_own_fighter_fails(
    client: TestClient, people: dict[str, Account]
) -> None:
    amir, bea = people["amir"], people["bea"]
    r = client.post(
        f"/fighters/{bea.profile_id}/weigh-ins",
        json={"weight_kg": 70.5, "measured_at": "2026-10-01T08:00:00Z"},
        headers=bea.headers,
    )
    assert r.status_code in (200, 201), r.text
    wid = r.json()["id"]
    r = client.delete(f"/fighters/{amir.profile_id}/weigh-ins/{wid}", headers=amir.headers)
    assert r.status_code == 404  # not Amir's weigh-in
    assert len(client.get(f"/fighters/{bea.profile_id}/weigh-ins", headers=bea.headers).json()) == 1

"""Privacy and consent (ADR-033): what's kept, who can see it, and requests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.services.terms import TERMS_VERSION
from tests.integration.test_access import Account, _signup


def test_a_fighter_sees_what_is_kept_and_who_can_see_it(client: TestClient) -> None:
    amir = _signup(client, "amir-p@alion.test", "fighter")
    carla = _signup(client, "carla-p@alion.test", "coach")
    me = client.get("/v2/privacy/me", headers=amir.headers).json()
    assert me["role"] == "fighter" and me["terms_version"] == TERMS_VERSION == me["terms_current"]
    assert me["terms_accepted_at"]
    kept = {h["what"]: h["count"] for h in me["holdings"]}
    assert kept["Training sessions (video clips, pose, punches)"] == 0
    assert me["viewers"] == {
        "coaches": [],
        "coaches_with_health": [],  # ADR-046: only the coaches the fighter shares them with
        "physicians": [],
        "gyms": [],
        "gym_managers": [],
    }

    # Amir makes Carla his coach: she now appears among those who can see his data.
    r = client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    assert r.status_code in (200, 201), r.text
    client.post(
        "/sessions",
        json={"fighter_id": amir.profile_id, "source": "live_webcam"},
        headers=amir.headers,
    )
    me = client.get("/v2/privacy/me", headers=amir.headers).json()
    assert len(me["viewers"]["coaches"]) == 1
    assert {h["what"]: h["count"] for h in me["holdings"]}[
        "Training sessions (video clips, pose, punches)"
    ] == 1

    # A coach sees their own account and notes, no fighter list.
    coach_me = client.get("/v2/privacy/me", headers=carla.headers).json()
    assert coach_me["viewers"] is None


def test_requests_are_one_open_per_kind_and_closed_by_an_admin(
    client: TestClient, admin_client: TestClient
) -> None:
    bea: Account = _signup(client, "bea-p@alion.test", "fighter")
    r = client.post(
        "/v2/privacy/requests",
        json={"kind": "export", "note": "for my records"},
        headers=bea.headers,
    )
    assert r.status_code == 201 and r.json()["status"] == "open"
    rid = r.json()["id"]
    assert (
        client.post(
            "/v2/privacy/requests", json={"kind": "export"}, headers=bea.headers
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/v2/privacy/requests", json={"kind": "withdraw"}, headers=bea.headers
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/v2/privacy/requests", json={"kind": "nonsense"}, headers=bea.headers
        ).status_code
        == 422
    )

    # Only admins and researchers see and close them.
    assert client.get("/v2/privacy/requests", headers=bea.headers).status_code == 403
    listed = admin_client.get("/v2/privacy/requests").json()
    assert {x["kind"] for x in listed} == {"export", "withdraw"} and listed[0][
        "user_email"
    ] == "bea-p@alion.test"
    done = admin_client.patch(
        f"/v2/privacy/requests/{rid}", json={"status": "done", "response": "Sent by email"}
    )
    assert done.status_code == 200 and done.json()["status"] == "done"
    assert (
        admin_client.patch(
            f"/v2/privacy/requests/{rid}", json={"status": "declined", "response": "x"}
        ).status_code
        == 409
    )

    # The person sees the answer, and can ask again once it's closed.
    mine = {
        x["kind"]: x for x in client.get("/v2/privacy/me", headers=bea.headers).json()["requests"]
    }
    assert mine["export"]["response"] == "Sent by email"
    assert (
        client.post(
            "/v2/privacy/requests", json={"kind": "export"}, headers=bea.headers
        ).status_code
        == 201
    )


def test_a_researcher_handles_requests_too(authed_client: TestClient, client: TestClient) -> None:
    fighter = _signup(client, "cem-p@alion.test", "fighter")
    client.post("/v2/privacy/requests", json={"kind": "withdraw"}, headers=fighter.headers)
    listed = authed_client.get("/v2/privacy/requests").json()  # authed_client is a researcher
    assert [x["kind"] for x in listed] == ["withdraw"]

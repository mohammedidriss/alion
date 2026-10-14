"""RQ1 ratings (ADR-036, ADR-045): only researchers and the coaches a researcher
chose rate; each score belongs to the signed-in rater under a code, a changed
score keeps the old one, and only researchers read everyone's."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_access import Account, _session, _signup


def _rate(
    client: TestClient, sid: str, headers: dict[str, str] | None, score: int, **extra: object
):  # type: ignore[no-untyped-def]
    return client.post(
        f"/studies/rq1/sessions/{sid}/ratings",
        json={"payload_mode": "fused", "criterion": "specificity", "score": score, **extra},
        headers=headers,
    )


def _coached(client: TestClient, tag: str) -> tuple[Account, Account, str]:
    """A fighter, a coach of theirs, and a session of the fighter's."""
    amir = _signup(client, f"amir-{tag}@alion.test", "fighter")
    carla = _signup(client, f"carla-{tag}@alion.test", "coach")
    client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    return amir, carla, _session(client, amir)


def test_only_chosen_raters_and_researchers_rate(
    client: TestClient, authed_client: TestClient
) -> None:
    amir, carla, sid = _coached(client, "c")
    for who in (amir, carla):  # a fighter, and a coach nobody chose
        assert client.get("/studies/rq1/me", headers=who.headers).json()["can_rate"] is False
        assert _rate(client, sid, who.headers, 4).status_code == 403
    assert authed_client.get("/studies/rq1/me").json()["can_rate"] is True  # a researcher

    # A researcher chooses Carla; a fighter can't be chosen; only researchers choose.
    assert (
        client.post(
            "/studies/rq1/raters", json={"email": "carla-c@alion.test"}, headers=carla.headers
        ).status_code
        == 403
    )
    assert (
        authed_client.post("/studies/rq1/raters", json={"email": "amir-c@alion.test"}).status_code
        == 422
    )
    r = authed_client.post("/studies/rq1/raters", json={"email": "CARLA-c@alion.test"})
    assert r.status_code == 201 and r.json()["rater_id"].startswith("R-")
    assert (
        authed_client.post("/studies/rq1/raters", json={"email": "carla-c@alion.test"}).status_code
        == 409
    )

    code = client.get("/studies/rq1/me", headers=carla.headers).json()
    assert code["can_rate"] is True
    rated = _rate(client, sid, carla.headers, 4, rater_id="coach_03")  # a typed id: ignored
    assert rated.status_code == 200 and rated.json()["rater_id"] == code["rater_id"]
    assert authed_client.get("/studies/rq1/raters").json()[0]["ratings"] == 1

    # Removed: no more rating; the score given stays.
    assert authed_client.delete(f"/studies/rq1/raters/{r.json()['user_id']}").status_code == 204
    assert _rate(client, sid, carla.headers, 5).status_code == 403
    assert [x["score"] for x in authed_client.get("/studies/rq1/ratings").json()] == [4]


def test_changing_a_score_keeps_the_old_one(authed_client: TestClient) -> None:
    fid = authed_client.post("/fighters", json={"name": "Rater", "stance": "orthodox"}).json()["id"]
    sid = authed_client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
        "id"
    ]
    _rate(authed_client, sid, None, 2)
    _rate(authed_client, sid, None, 2)  # the same again: no new version
    _rate(authed_client, sid, None, 5)

    mine = authed_client.get(f"/studies/rq1/sessions/{sid}/ratings").json()
    assert [r["score"] for r in mine] == [5]
    assert [r["score"] for r in authed_client.get("/studies/rq1/ratings").json()] == [5]
    every = authed_client.get("/studies/rq1/ratings", params={"history": True}).json()
    assert [(r["score"], r["superseded_at"] is None) for r in every] == [(2, False), (5, True)]


def test_raters_never_see_each_others_scores(client: TestClient, authed_client: TestClient) -> None:
    amir, carla, sid = _coached(client, "x")
    dana = _signup(client, "dana-x@alion.test", "coach")
    client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": dana.profile_id, "role": "striking"},
        headers=amir.headers,
    )
    for email in ("carla-x@alion.test", "dana-x@alion.test"):
        authed_client.post("/studies/rq1/raters", json={"email": email})
    assert _rate(client, sid, carla.headers, 1).status_code == 200
    assert _rate(client, sid, dana.headers, 5).status_code == 200
    theirs = client.get(f"/studies/rq1/sessions/{sid}/ratings", headers=dana.headers).json()
    assert [r["score"] for r in theirs] == [5]
    # The bulk read is for researchers only.
    assert client.get("/studies/rq1/ratings", headers=dana.headers).status_code == 403

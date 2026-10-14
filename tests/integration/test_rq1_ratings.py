"""RQ1 ratings (ADR-036): each score belongs to the signed-in rater under a code,
a changed score keeps the old one, and only researchers read everyone's."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_access import _session, _signup


def _rate(client: TestClient, sid: str, headers: dict[str, str], score: int, **extra: object):  # type: ignore[no-untyped-def]
    return client.post(
        f"/studies/rq1/sessions/{sid}/ratings",
        json={"payload_mode": "fused", "criterion": "specificity", "score": score, **extra},
        headers=headers,
    )


def test_a_score_is_the_signed_in_raters_and_a_typed_id_is_ignored(client: TestClient) -> None:
    amir = _signup(client, "amir-r@alion.test", "fighter")
    sid = _session(client, amir)
    code = client.get("/studies/rq1/me", headers=amir.headers).json()["rater_id"]
    assert code.startswith("R-") and len(code) == 10

    r = _rate(client, sid, amir.headers, 4, rater_id="coach_03")  # someone else's id: ignored
    assert r.status_code == 200 and r.json()["rater_id"] == code


def test_changing_a_score_keeps_the_old_one(client: TestClient, authed_client: TestClient) -> None:
    amir = _signup(client, "amir-h@alion.test", "fighter")
    sid = _session(client, amir)
    _rate(client, sid, amir.headers, 2)
    _rate(client, sid, amir.headers, 2)  # the same again: no new version
    _rate(client, sid, amir.headers, 5)

    mine = client.get(f"/studies/rq1/sessions/{sid}/ratings", headers=amir.headers).json()
    assert [r["score"] for r in mine] == [5]

    current = authed_client.get("/studies/rq1/ratings").json()  # a researcher
    assert [r["score"] for r in current] == [5]
    every = authed_client.get("/studies/rq1/ratings", params={"history": True}).json()
    assert [(r["score"], r["superseded_at"] is None) for r in every] == [(2, False), (5, True)]


def test_raters_never_see_each_others_scores(client: TestClient) -> None:
    amir = _signup(client, "amir-x@alion.test", "fighter")
    carla = _signup(client, "carla-x@alion.test", "coach")
    client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    sid = _session(client, amir)
    _rate(client, sid, amir.headers, 1)
    assert _rate(client, sid, carla.headers, 5).status_code == 200
    theirs = client.get(f"/studies/rq1/sessions/{sid}/ratings", headers=carla.headers).json()
    assert [r["score"] for r in theirs] == [5]
    # The bulk read is for researchers only.
    assert client.get("/studies/rq1/ratings", headers=carla.headers).status_code == 403

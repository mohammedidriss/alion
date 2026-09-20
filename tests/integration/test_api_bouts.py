"""Two-fighter bouts — creation, corner-assignment rules, participants, result (ADR-011)."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient


def _make_fighter(client: TestClient, name: str = "F") -> str:
    return client.post("/fighters", json={"name": name}).json()["id"]


def _make_session(client: TestClient, fighter_id: str) -> str:
    return client.post(
        "/sessions", json={"fighter_id": fighter_id, "source": "live_webcam"}
    ).json()["id"]


def test_bout_create_and_corner_assignment(authed_client: TestClient) -> None:
    red_s = _make_session(authed_client, _make_fighter(authed_client, "Red"))
    blue_s = _make_session(authed_client, _make_fighter(authed_client, "Blue"))

    bout = authed_client.post(
        "/bouts", json={"label": "R v B", "round_count": 12, "round_duration_s": 180}
    )
    assert bout.status_code == 201
    bid = bout.json()["id"]
    assert bout.json()["round_count"] == 12

    r = authed_client.post(
        f"/bouts/{bid}/participants", json={"session_id": red_s, "corner": "red"}
    )
    assert r.status_code == 200
    assert r.json()["corner"] == "red" and r.json()["bout_id"] == bid
    b = authed_client.post(
        f"/bouts/{bid}/participants", json={"session_id": blue_s, "corner": "blue"}
    )
    assert b.status_code == 200 and b.json()["corner"] == "blue"

    parts = authed_client.get(f"/bouts/{bid}/participants").json()
    assert len(parts) == 2 and {p["corner"] for p in parts} == {"red", "blue"}

    # The session itself reports its bout + corner (additive SessionRead fields).
    sess = authed_client.get(f"/sessions/{red_s}").json()
    assert sess["bout_id"] == bid and sess["corner"] == "red"


def test_corner_taken_and_two_max(authed_client: TestClient) -> None:
    s1, s2, s3 = (
        _make_session(authed_client, _make_fighter(authed_client, n)) for n in ("A", "B", "C")
    )
    bid = authed_client.post("/bouts", json={}).json()["id"]

    authed_client.post(f"/bouts/{bid}/participants", json={"session_id": s1, "corner": "red"})
    dup = authed_client.post(f"/bouts/{bid}/participants", json={"session_id": s2, "corner": "red"})
    assert dup.status_code == 409  # red corner already taken

    authed_client.post(f"/bouts/{bid}/participants", json={"session_id": s2, "corner": "blue"})
    third = authed_client.post(
        f"/bouts/{bid}/participants", json={"session_id": s3, "corner": "red"}
    )
    assert third.status_code == 409  # both corners full


def test_session_belongs_to_one_bout(authed_client: TestClient) -> None:
    s = _make_session(authed_client, _make_fighter(authed_client, "X"))
    b1 = authed_client.post("/bouts", json={}).json()["id"]
    b2 = authed_client.post("/bouts", json={}).json()["id"]
    authed_client.post(f"/bouts/{b1}/participants", json={"session_id": s, "corner": "red"})
    clash = authed_client.post(f"/bouts/{b2}/participants", json={"session_id": s, "corner": "red"})
    assert clash.status_code == 409  # already in another bout


def test_remove_participant_and_result(authed_client: TestClient) -> None:
    s = _make_session(authed_client, _make_fighter(authed_client, "Y"))
    bid = authed_client.post("/bouts", json={}).json()["id"]
    authed_client.post(f"/bouts/{bid}/participants", json={"session_id": s, "corner": "red"})

    rm = authed_client.delete(f"/bouts/{bid}/participants/{s}")
    assert rm.status_code == 200
    assert rm.json()["bout_id"] is None and rm.json()["corner"] is None
    assert authed_client.get(f"/bouts/{bid}/participants").json() == []

    res = authed_client.patch(
        f"/bouts/{bid}/result", json={"winner_corner": "red", "result_method": "TKO"}
    )
    assert res.status_code == 200
    assert res.json()["winner_corner"] == "red" and res.json()["result_method"] == "TKO"


def test_unknown_bout_404(authed_client: TestClient) -> None:
    assert authed_client.get(f"/bouts/{uuid4()}").status_code == 404
    assert (
        authed_client.post(
            f"/bouts/{uuid4()}/participants", json={"session_id": str(uuid4()), "corner": "red"}
        ).status_code
        == 404
    )

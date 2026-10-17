"""The fight card (ADR-069): what kind of fight, the belts on the line, the event,
the weight and weigh-ins, the officials — and deleting a fight keeps its recordings."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _fighter(client: TestClient, name: str) -> str:
    return client.post("/fighters", json={"name": name}).json()["id"]


def _session(client: TestClient, fighter_id: str) -> str:
    return client.post(
        "/sessions", json={"fighter_id": fighter_id, "source": "live_webcam"}
    ).json()["id"]


def _fight(client: TestClient, **card: object) -> str:
    r = client.post("/bouts", json=card)
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    for corner, name in (("red", "Red Corner"), ("blue", "Blue Corner")):
        sid = _session(client, _fighter(client, name))
        assert (
            client.post(
                f"/bouts/{bid}/participants", json={"session_id": sid, "corner": corner}
            ).status_code
            == 200
        )
    return bid


def test_a_title_fight_carries_its_whole_card(authed_client: TestClient) -> None:
    bid = _fight(
        authed_client,
        label="Red v Blue",
        fight_type="pro_title",
        titles=[{"body": "WBC", "kind": "world"}, {"body": "IBF", "kind": "world"}],
        event_name="Fight Night 12",
        venue="Madison Square Garden",
        city="New York",
        country="USA",
        weight_class="welterweight",
        referee="Jane Ref",
        judges=["A", " ", "C"],
        promoter="Top Rank",
        broadcaster="DAZN",
        round_count=12,
    )
    card = authed_client.get(f"/bouts/{bid}").json()
    assert card["fight_type"] == "pro_title"
    assert [t["body"] for t in card["titles"]] == ["WBC", "IBF"]
    assert card["venue"] == "Madison Square Garden" and card["city"] == "New York"
    assert card["weight_limit_kg"] == 66.7  # welterweight, 147 lb — filled in for a division
    assert card["judges"] == ["A", "C"]  # blanks dropped
    assert card["promoter"] == "Top Rank" and card["broadcaster"] == "DAZN"


def test_belts_belong_to_title_fights_only(authed_client: TestClient) -> None:
    r = authed_client.post("/bouts", json={"fight_type": "pro_title"})
    assert r.status_code == 422 and "belt" in r.json()["detail"]
    r = authed_client.post(
        "/bouts", json={"fight_type": "sparring", "titles": [{"body": "WBA", "kind": "super"}]}
    )
    assert r.status_code == 422
    r = authed_client.post(
        "/bouts", json={"fight_type": "pro_title", "titles": [{"body": "XYZ", "kind": "world"}]}
    )
    assert r.status_code == 422
    r = authed_client.post("/bouts", json={"fight_type": "pro", "weight_class": "featherweightish"})
    assert r.status_code == 422


def test_a_friendly_and_a_catchweight(authed_client: TestClient) -> None:
    r = authed_client.post("/bouts", json={"fight_type": "sparring", "weight_limit_kg": 70.3})
    assert r.status_code == 201
    assert r.json()["fight_type"] == "sparring" and r.json()["titles"] == []
    assert r.json()["weight_limit_kg"] == 70.3 and r.json()["weight_class"] is None


def test_weigh_ins_and_officials_are_added_later(authed_client: TestClient) -> None:
    bid = _fight(
        authed_client,
        fight_type="pro_title",
        titles=[{"body": "WBA", "kind": "super"}],
        weight_class="lightweight",
    )
    r = authed_client.patch(
        f"/bouts/{bid}", json={"red_weigh_in_kg": 61.1, "blue_weigh_in_kg": 61.4, "referee": "Ref"}
    )
    assert r.status_code == 200, r.text
    card = r.json()
    assert card["red_weigh_in_kg"] == 61.1 and card["blue_weigh_in_kg"] == 61.4
    assert card["titles"] == [{"body": "WBA", "kind": "super"}]  # untouched
    # Turning it into a non-title fight takes the belts off the line.
    card = authed_client.patch(f"/bouts/{bid}", json={"fight_type": "pro"}).json()
    assert card["fight_type"] == "pro" and card["titles"] == []


def test_options_list_the_bodies_and_divisions(authed_client: TestClient) -> None:
    opts = authed_client.get("/bouts/options").json()
    assert {"WBA", "WBC", "IBF", "WBO", "The Ring"} <= set(opts["sanctioning_bodies"])
    assert [t["key"] for t in opts["fight_types"]] == [
        "pro_title",
        "pro",
        "amateur",
        "exhibition",
        "sparring",
    ]
    heavy = next(w for w in opts["weight_classes"] if w["key"] == "heavyweight")
    assert heavy["limit_lb"] is None
    middle = next(w for w in opts["weight_classes"] if w["key"] == "middleweight")
    assert middle["limit_lb"] == 160 and middle["limit_kg"] == 72.6


def test_deleting_a_fight_hides_it_and_keeps_its_recordings(authed_client: TestClient) -> None:
    bid = _fight(authed_client, label="To delete")
    corners = authed_client.get(f"/bouts/{bid}/participants").json()
    assert authed_client.delete(f"/bouts/{bid}").status_code == 204
    assert authed_client.get(f"/bouts/{bid}").status_code == 404
    assert bid not in {b["id"] for b in authed_client.get("/bouts").json()}
    # The corners' sessions are deleted from view, not destroyed (ADR-056).
    for s in corners:
        assert authed_client.get(f"/sessions/{s['id']}").status_code in (404, 200)
    assert authed_client.delete(f"/bouts/{bid}").status_code == 404

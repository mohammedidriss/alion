"""Fights through the camera studio (ADR-063): linked phones follow an open fight,
each into its own corner's session, with corners picked once and remembered."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_access import _signup


@pytest.fixture
def capture_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.routes import capture_coord, studio

    monkeypatch.setattr(capture_coord, "_STATE_DIR", tmp_path / "capture")
    monkeypatch.setattr(capture_coord, "_VIDEO_DIR", tmp_path / "clips")
    monkeypatch.setattr(studio, "_STATE_DIR", tmp_path / "capture")
    yield tmp_path


def _fight(
    client: TestClient, corners: tuple[str, ...] = ("red", "blue")
) -> tuple[str, dict[str, str]]:
    bid = client.post("/bouts", json={"label": "R v B"}).json()["id"]
    sessions = {}
    for corner in corners:
        fid = client.post("/fighters", json={"name": f"{corner} fighter"}).json()["id"]
        sid = client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()[
            "id"
        ]
        r = client.post(f"/bouts/{bid}/participants", json={"session_id": sid, "corner": corner})
        assert r.status_code == 200, r.text
        sessions[corner] = sid
    return bid, sessions


def _token(client: TestClient) -> str:
    path = client.get("/v2/studio").json()["join_path"]
    return parse_qs(urlparse(path).query)["studio"][0]


def _poll(client: TestClient, token: str, phone: str) -> dict:  # type: ignore[type-arg]
    r = client.get("/studio/state", params={"token": token, "phone_id": phone, "label": phone})
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_each_linked_phone_joins_its_corner(authed_client: TestClient, capture_dirs: Path) -> None:
    bid, sessions = _fight(authed_client)
    st = authed_client.put("/v2/studio/active", json={"kind": "bout", "id": bid})
    assert st.status_code == 200 and st.json()["active"]["kind"] == "bout"
    token = _token(authed_client)

    # A new phone waits until it has a corner, and the fight page lists it.
    assert _poll(authed_client, token, "front") == {
        "active": None,
        "note": "Pick this phone's corner on the fight page",
    }
    phones = authed_client.get("/v2/studio").json()["phones"]
    assert phones == [{"phone_id": "front", "label": "front", "corner": None}]

    authed_client.put("/v2/studio/phones/front/corner", json={"corner": "red"})
    authed_client.put("/v2/studio/phones/left/corner", json={"corner": "blue"})
    red = _poll(authed_client, token, "front")["active"]
    blue = _poll(authed_client, token, "left")["active"]
    assert (red["kind"], red["id"], red["corner"], red["bout_id"]) == (
        "session",
        sessions["red"],
        "red",
        bid,
    )
    assert (blue["id"], blue["corner"]) == (sessions["blue"], "blue")

    # It joins with that corner's token, like a phone that scanned the corner's QR.
    r = authed_client.post(
        f"/sessions/{sessions['red']}/multicam/register",
        json={"token": red["join_token"], "label": "front"},
    )
    assert r.status_code == 200, r.text
    assert [
        d["label"]
        for d in authed_client.get(f"/sessions/{sessions['red']}/multicam/devices").json()
    ] == ["front"]


def test_corners_are_remembered_for_the_next_fight_and_for_a_restart(
    authed_client: TestClient, capture_dirs: Path
) -> None:
    from api.routes import studio

    first, _ = _fight(authed_client)
    authed_client.put("/v2/studio/active", json={"kind": "bout", "id": first})
    authed_client.put("/v2/studio/phones/front/corner", json={"corner": "red"})
    second, sessions = _fight(authed_client)
    authed_client.put("/v2/studio/active", json={"kind": "bout", "id": second})
    studio._active.clear()  # what a uvicorn reload does
    studio._phones.clear()
    token = _token(authed_client)
    assert _poll(authed_client, token, "front")["active"]["id"] == sessions["red"]

    # "Off": it sits fights out — but still joins a training session.
    authed_client.put("/v2/studio/phones/front/corner", json={"corner": None})
    assert _poll(authed_client, token, "front")["active"] is None
    authed_client.put("/v2/studio/active", json={"kind": "session", "id": sessions["blue"]})
    joined = _poll(authed_client, token, "front")["active"]
    assert (joined["id"], joined["corner"]) == (sessions["blue"], None)


def test_a_missing_corner_or_someone_elses_fight(
    client: TestClient, authed_client: TestClient, capture_dirs: Path
) -> None:
    bid, _ = _fight(authed_client, corners=("red",))
    authed_client.put("/v2/studio/active", json={"kind": "bout", "id": bid})
    authed_client.put("/v2/studio/phones/left/corner", json={"corner": "blue"})
    assert _poll(authed_client, _token(authed_client), "left")["note"] == (
        "This fight has no blue corner yet"
    )

    # A coach with neither fighter can't point their phones at this fight.
    coach = _signup(client, "carla-f@alion.test", "coach")
    r = client.put("/v2/studio/active", json={"kind": "bout", "id": bid}, headers=coach.headers)
    assert r.status_code == 403

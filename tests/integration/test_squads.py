"""Squads (ADR-053): groups within a gym run by its owners, managers and head
coaches; a squad's fighters are the gym's members and its coaches the gym's
coaching staff; a squad coach sees the squad's fighters' training while both are
on it and the squad is open; sessions record the squad they're trained with."""

from __future__ import annotations

import datetime as dt

from fastapi.testclient import TestClient

from tests.integration.test_access import Account, _session, _signup
from tests.integration.test_gym_invitations import _import, _manager


def _member(client: TestClient, gym: str, gina: dict[str, str], who: Account) -> None:
    mid = _import(client, gym, who, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=who.headers)


def _coach(client: TestClient, gym: str, gina: dict[str, str], who: Account) -> int:
    sid = _import(client, gym, who, gina).json()["id"]
    client.post(f"/v2/my-staff/{sid}/accept", headers=who.headers)
    return int(sid)


def _gym(client: TestClient, tag: str):  # type: ignore[no-untyped-def]
    gina, gym = _manager(client, f"gina-{tag}@alion.test", f"Gym {tag}")
    amir = _signup(client, f"amir-{tag}@alion.test", "fighter")
    bea = _signup(client, f"bea-{tag}@alion.test", "fighter")
    carla = _signup(client, f"carla-{tag}@alion.test", "coach")
    for f in (amir, bea):
        _member(client, gym, gina, f)
    staff_id = _coach(client, gym, gina, carla)
    return gina, gym, amir, bea, carla, staff_id


def _squad(client: TestClient, gym: str, gina: dict[str, str], name: str, **kw: object) -> str:
    r = client.post(f"/gyms/{gym}/squads", json={"name": name, **kw}, headers=gina)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def test_a_squad_coach_sees_its_fighters_while_both_are_on_it(client: TestClient) -> None:
    gina, gym, amir, bea, carla, _ = _gym(client, "sq1")
    zed = _signup(client, "zed-sq1@alion.test", "fighter")  # not the gym's
    dana = _signup(client, "dana-sq1@alion.test", "coach")  # not the gym's staff
    a_sid, b_sid = _session(client, amir), _session(client, bea)

    assert (
        client.post(f"/gyms/{gym}/squads", json={"name": "X"}, headers=carla.headers).status_code
        == 403
    )
    sq = _squad(client, gym, gina, "Pro team")
    members, staff = f"/squads/{sq}/members", f"/squads/{sq}/staff"
    assert (
        client.post(members, json={"fighter_id": zed.profile_id}, headers=gina).status_code == 422
    )
    r = client.post(members, json={"fighter_id": amir.profile_id}, headers=gina)
    assert r.status_code == 201, r.text
    assert (
        client.post(members, json={"fighter_id": amir.profile_id}, headers=gina).status_code == 409
    )
    assert client.post(staff, json={"coach_id": dana.profile_id}, headers=gina).status_code == 422
    assert client.post(staff, json={"coach_id": carla.profile_id}, headers=gina).status_code == 201

    assert client.get(f"/sessions/{a_sid}", headers=carla.headers).status_code == 200
    assert client.get(f"/sessions/{b_sid}", headers=carla.headers).status_code == 403
    (mine,) = client.get("/v2/my-squads", headers=carla.headers).json()
    assert [m["name"] for m in mine["members"]] == ["Amir-Sq1"]
    assert [
        s["name"]
        for s in client.get(f"/fighters/{amir.profile_id}/squads", headers=amir.headers).json()
    ] == ["Pro team"]
    assert client.get(f"/squads/{sq}", headers=bea.headers).status_code == 403  # not on it

    # Off the squad: no more access.
    member_id = client.get(f"/squads/{sq}", headers=gina).json()["members"][0]["id"]
    client.post(f"{members}/{member_id}/end", headers=gina)
    assert client.get(f"/sessions/{a_sid}", headers=carla.headers).status_code == 403
    # A camp past its last day, or an archived squad: no access either.
    client.post(members, json={"fighter_id": bea.profile_id}, headers=gina)
    assert client.get(f"/sessions/{b_sid}", headers=carla.headers).status_code == 200
    yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
    client.patch(f"/squads/{sq}", json={"kind": "camp", "ends_on": yesterday}, headers=gina)
    assert client.get(f"/sessions/{b_sid}", headers=carla.headers).status_code == 403
    client.patch(f"/squads/{sq}", json={"ends_on": None}, headers=gina)
    assert client.get(f"/sessions/{b_sid}", headers=carla.headers).status_code == 200
    assert client.post(f"/squads/{sq}/archive", headers=gina).json()["open"] is False
    assert client.get(f"/sessions/{b_sid}", headers=carla.headers).status_code == 403


def test_sessions_record_the_main_squad_and_the_week_shows(client: TestClient) -> None:
    gina, gym, amir, bea, carla, _ = _gym(client, "sq2")
    a = _squad(client, gym, gina, "Amateurs")
    b = _squad(client, gym, gina, "Strength group", kind="class")
    client.post(
        f"/squads/{a}/members", json={"fighter_id": amir.profile_id, "is_main": True}, headers=gina
    )
    client.post(f"/squads/{b}/members", json={"fighter_id": amir.profile_id}, headers=gina)

    r = client.post(
        "/sessions",
        json={"fighter_id": amir.profile_id, "source": "live_webcam"},
        headers=amir.headers,
    )
    assert r.status_code == 201 and (r.json()["squad_id"], r.json()["gym_id"]) == (a, gym)
    body = {"fighter_id": bea.profile_id, "source": "live_webcam", "squad_id": a}
    assert client.post("/sessions", json=body, headers=bea.headers).status_code == 422  # not on it

    weekly = {s["name"]: s for s in client.get(f"/gyms/{gym}/squads", headers=gina).json()}
    assert (weekly["Amateurs"]["sessions_7d"], weekly["Amateurs"]["trained_7d"]) == (1, 1)
    assert weekly["Strength group"]["sessions_7d"] == 0
    # A gym coach who doesn't coach the squad sees it, not its training numbers.
    assert client.get(f"/gyms/{gym}/squads", headers=carla.headers).json()[0]["sessions_7d"] is None

    # One main squad: the fighter moves it.
    member_b = next(m for m in client.get(f"/squads/{b}", headers=gina).json()["members"])
    client.patch(
        f"/squads/{b}/members/{member_b['id']}", json={"is_main": True}, headers=amir.headers
    )
    mains = [
        s["name"]
        for s in client.get(f"/fighters/{amir.profile_id}/squads", headers=amir.headers).json()
    ]
    assert mains[0] == "Strength group"
    r = client.post(
        "/sessions",
        json={"fighter_id": amir.profile_id, "source": "live_webcam"},
        headers=amir.headers,
    )
    assert r.json()["squad_id"] == b


def test_leaving_the_gym_ends_squad_places(client: TestClient) -> None:
    gina, gym, amir, _bea, carla, staff_id = _gym(client, "sq3")
    sq = _squad(client, gym, gina, "Pros")
    client.post(f"/squads/{sq}/members", json={"fighter_id": amir.profile_id}, headers=gina)
    client.post(f"/squads/{sq}/staff", json={"coach_id": carla.profile_id}, headers=gina)
    sid = _session(client, amir)
    assert client.get(f"/sessions/{sid}", headers=carla.headers).status_code == 200

    (mine,) = client.get("/v2/my-gyms", headers=amir.headers).json()
    client.post(f"/v2/my-gyms/{mine['id']}/leave", headers=amir.headers)
    detail = client.get(f"/squads/{sq}", headers=gina).json()
    assert (
        detail["members"] == []
        and client.get(f"/sessions/{sid}", headers=carla.headers).status_code == 403
    )

    client.post(f"/gyms/{gym}/staff/{staff_id}/end", headers=gina)
    assert client.get(f"/squads/{sq}", headers=gina).json()["staff"] == []

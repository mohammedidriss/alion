"""The gym workflow, step 1 (ADR-050): a fighter leaves a gym on their own; leaving
— or being removed — ends the coach links made through the gym (ADR-052: the ones
its staff made), history kept; only the gym's active or trial members check in."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.integration.test_access import Account, _session, _signup
from tests.integration.test_gym_invitations import _import, _manager


def _coach_of(
    client: TestClient, fighter: Account, coach: Account, by: dict[str, str] | None = None
) -> None:
    r = client.post(
        f"/fighters/{fighter.profile_id}/coach-assignments",
        json={"coach_id": coach.profile_id, "role": "head_coach"},
        headers=by or fighter.headers,
    )
    assert r.status_code == 201, r.text


def _open_coaches(session: Session, fighter: Account) -> set[str]:
    from store import CoachAssignment

    session.expire_all()
    rows = session.exec(select(CoachAssignment).where(CoachAssignment.ended_on == None))  # noqa: E711
    return {str(a.coach_id) for a in rows if str(a.fighter_id) == fighter.profile_id}


def _staff_coach(client: TestClient, gym: str, gina: dict[str, str], coach: Account) -> int:
    """The gym invites a coach to its staff and they accept."""
    sid = _import(client, gym, coach, gina).json()["id"]
    r = client.post(f"/v2/my-staff/{sid}/accept", headers=coach.headers)
    assert r.status_code == 200, r.text
    return int(sid)


def test_a_fighter_leaves_a_gym_and_its_ties_end(client: TestClient, session: Session) -> None:
    gina, gym = _manager(client, "gina-w@alion.test", "Westside")
    amir = _signup(client, "amir-w@alion.test", "fighter")
    carla = _signup(client, "carla-w@alion.test", "coach")  # the gym's coach
    dana = _signup(client, "dana-w@alion.test", "coach")  # Amir's own, not the gym's
    sid = _session(client, amir)
    _staff_coach(client, gym, gina, carla)
    mid = _import(client, gym, amir, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    _coach_of(client, amir, carla, by=gina)  # through the gym
    _coach_of(client, amir, dana)  # Amir's own
    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 200

    (mine,) = client.get("/v2/my-gyms", headers=amir.headers).json()
    assert mine["gym_name"] == "Westside" and mine["status"] == "active"
    # Only Amir leaves his own gym.
    assert client.post(f"/v2/my-gyms/{mid}/leave", headers=dana.headers).status_code == 404
    assert client.post(f"/v2/my-gyms/{mid}/leave", headers=amir.headers).status_code == 200

    assert client.get(f"/sessions/{sid}", headers=gina).status_code == 403
    assert _open_coaches(session, amir) == {dana.profile_id}  # the gym's link ended
    assert client.get("/v2/my-gyms", headers=amir.headers).json() == []
    assert client.get(f"/fighters/{amir.profile_id}", headers=amir.headers).json()["gym_id"] is None
    assert client.post(f"/v2/my-gyms/{mid}/leave", headers=amir.headers).status_code == 404


def test_a_coach_removed_from_a_gym_stops_coaching_its_fighters(
    client: TestClient, session: Session
) -> None:
    gina, gym = _manager(client, "gina-c@alion.test", "Eastside")
    amir = _signup(client, "amir-c2@alion.test", "fighter")
    carla = _signup(client, "carla-c2@alion.test", "coach")
    staff_id = _staff_coach(client, gym, gina, carla)
    mid = _import(client, gym, amir, gina).json()["id"]
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    _coach_of(client, amir, carla, by=gina)

    assert client.post(f"/gyms/{gym}/staff/{staff_id}/end", headers=gina).status_code == 200
    assert _open_coaches(session, amir) == set()


def test_only_active_or_trial_members_check_in(client: TestClient) -> None:
    gina, gym = _manager(client, "gina-k@alion.test", "Checkpoint")
    amir = _signup(client, "amir-k@alion.test", "fighter")
    body = {"member_id": amir.profile_id, "member_type": "fighter"}
    url = f"/gyms/{gym}/checkins"
    assert client.post(url, json=body, headers=gina).status_code == 409  # not a member
    mid = _import(client, gym, amir, gina).json()["id"]
    assert client.post(url, json=body, headers=gina).status_code == 409  # only invited
    client.post(f"/v2/gym-invitations/{mid}/accept", headers=amir.headers)
    assert client.post(url, json=body, headers=gina).status_code == 201

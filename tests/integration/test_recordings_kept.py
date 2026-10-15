"""Recordings are never deleted (ADR-056): deleting a profile keeps its sessions,
heart rate and wrist data; the login can be deleted alone; only the fighter or an
administrator deletes a profile someone signs in to; a session with sensor data
but no camera frames is never purged as empty."""

from __future__ import annotations

import datetime as dt
from uuid import UUID

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from tests.integration.test_access import _session, _signup


def _login(client: TestClient, email: str) -> int:
    return client.post(
        "/auth/login", data={"username": email, "password": "ValidPass123"}
    ).status_code


def _hr(session: Session, sid: str) -> None:
    from store import HRSampleRow

    session.add(HRSampleRow(session_id=UUID(sid), t_ms=0.0, rr_ms=430.0, hr_bpm=140.0))
    session.commit()


def test_deleting_a_profile_keeps_its_recordings(
    client: TestClient, authed_client: TestClient, admin_client: TestClient, session: Session
) -> None:
    from store import HRSampleRow

    amir = _signup(client, "amir-k@alion.test", "fighter")
    carla = _signup(client, "carla-k@alion.test", "coach")
    client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    sid = _session(client, amir)
    _hr(session, sid)
    # A coach doesn't delete a profile someone signs in to.
    opts = client.get(f"/fighters/{amir.profile_id}/removal", headers=carla.headers).json()
    assert opts["can_delete_profile"] is False and opts["note"]
    assert client.delete(f"/fighters/{amir.profile_id}", headers=carla.headers).status_code == 403

    mine = client.get(f"/fighters/{amir.profile_id}/removal", headers=amir.headers).json()
    assert mine == {
        **mine,
        "has_account": True,
        "can_delete_profile": True,
        "can_delete_account": True,
    }
    assert client.delete(f"/fighters/{amir.profile_id}", headers=amir.headers).status_code == 204

    assert _login(client, "amir-k@alion.test") == 401  # the login went with it
    assert client.get(f"/sessions/{sid}", headers=carla.headers).status_code == 403  # gone for her
    # The recording stays — for the study, and the models.
    assert authed_client.get(f"/sessions/{sid}").status_code == 200
    session.expire_all()
    assert (
        len(session.exec(select(HRSampleRow).where(HRSampleRow.session_id == UUID(sid))).all()) == 1
    )
    # An administrator restores the profile; its login on the People page.
    assert admin_client.post(f"/fighters/{amir.profile_id}/restore").json()["removed_at"] is None


def test_deleting_the_login_only_keeps_the_profile(client: TestClient) -> None:
    amir = _signup(client, "amir-l@alion.test", "fighter")
    carla = _signup(client, "carla-l@alion.test", "coach")
    client.post(
        f"/fighters/{amir.profile_id}/coach-assignments",
        json={"coach_id": carla.profile_id, "role": "head_coach"},
        headers=amir.headers,
    )
    sid = _session(client, amir)
    r = client.post(f"/fighters/{amir.profile_id}/remove-account", headers=amir.headers)
    assert r.status_code == 200, r.text
    assert _login(client, "amir-l@alion.test") == 401
    # The profile and its sessions stay where they were.
    assert (
        client.get(f"/fighters/{amir.profile_id}", headers=carla.headers).json()["removed_at"]
        is None
    )
    assert client.get(f"/sessions/{sid}", headers=carla.headers).status_code == 200


def test_a_profile_nobody_signs_in_to_is_deleted_by_its_coach_and_a_researcher_keeps_theirs(
    client: TestClient, authed_client: TestClient
) -> None:
    fid = authed_client.post("/fighters", json={"name": "Walk-in", "stance": "orthodox"}).json()[
        "id"
    ]
    opts = authed_client.get(f"/fighters/{fid}/removal").json()
    assert opts["has_account"] is False and opts["can_delete_profile"] is True
    assert authed_client.delete(f"/fighters/{fid}").status_code == 204

    # The researcher's own profile isn't deleted from their own account.
    me = authed_client.get("/auth/me").json()
    if me["profile_id"] and me["role"] == "fighter":  # (the test researcher is a coach)
        assert (
            authed_client.get(f"/fighters/{me['profile_id']}/removal").json()["can_delete_profile"]
            is False
        )


def test_a_session_with_sensor_data_is_never_purged_as_empty(
    client: TestClient, session: Session
) -> None:
    from store import Session as SessionRow

    amir = _signup(client, "amir-p@alion.test", "fighter")
    empty, sensors = _session(client, amir), _session(client, amir)
    _hr(session, sensors)
    old = dt.datetime.utcnow() - dt.timedelta(hours=1)
    for sid in (empty, sensors):
        row = session.get(SessionRow, UUID(sid))
        assert row is not None
        row.started_at = old
        session.add(row)
    session.commit()

    client.delete("/sessions/stale-pending", headers=amir.headers)
    session.expire_all()
    assert session.get(SessionRow, UUID(sensors)) is not None  # heart rate, no camera: kept
    assert session.get(SessionRow, UUID(empty)) is None  # nothing recorded: tidied away

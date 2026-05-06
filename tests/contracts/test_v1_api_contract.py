"""Locked Phase 1 API contract — runs on every commit.

These tests pin the *shape* of the v1 API surface so future phases can't
silently break Phase 1 consumers (the existing dashboard, any external
tooling, the validation-study scripts when they land).

Rules of this file:
- Failures here MUST NOT be fixed by relaxing assertions; if a v1 endpoint
  ever needs to change shape, that is a versioning event — bump to /v2 and
  leave /v1 alone.
- New Phase 2+ work goes in a separate test file and a separate prefix.

Tests target the /v1 surface explicitly. Unversioned aliases share the
same router so they're implicitly covered.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

V1 = "/v1"

# ---------- Health & capabilities ----------


def test_v1_health_shape(client: TestClient) -> None:
    r = client.get(f"{V1}/health")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"status", "schema_version"}
    assert body["status"] == "ok"
    assert isinstance(body["schema_version"], str)


def test_v1_capabilities_shape(client: TestClient) -> None:
    r = client.get(f"{V1}/health/capabilities")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"cv_available", "cv_reason", "webcam_likely"}


# ---------- Cameras ----------


def test_v1_cameras_shape(client: TestClient) -> None:
    r = client.get(f"{V1}/cameras")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"cameras", "cv_available", "reason"}
    assert isinstance(body["cameras"], list)


# ---------- Fighter options + CRUD ----------


def test_v1_fighter_options_shape(client: TestClient) -> None:
    r = client.get(f"{V1}/fighters/options")
    assert r.status_code == 200
    body = r.json()
    assert {"stances", "hands", "skill_levels", "weight_classes", "sexes"} <= set(body.keys())
    # Stance values are part of the contract — frozen.
    assert set(body["stances"]) == {"orthodox", "southpaw", "switch"}


def test_v1_fighter_full_crud_round_trip(client: TestClient) -> None:
    # Create
    r = client.post(f"{V1}/fighters", json={"name": "v1-test", "stance": "orthodox"})
    assert r.status_code == 201
    fighter = r.json()
    fid = fighter["id"]

    # Required keys on FighterRead — every one of these is part of the v1 contract.
    required = {
        "id",
        "name",
        "nickname",
        "dob",
        "nationality",
        "sex",
        "stance",
        "dominant_hand",
        "height_cm",
        "reach_cm",
        "weight_kg",
        "shoulder_width_cm",
        "skill_level",
        "weight_class",
        "years_training",
        "gym",
        "trainer",
        "record_wins",
        "record_losses",
        "record_draws",
        "record_kos",
        "boxrec_id",
        "usa_boxing_id",
        "notes",
        "created_at",
    }
    assert required <= set(fighter.keys()), f"missing: {required - set(fighter.keys())}"

    # Patch all fields
    patch = {
        "nickname": "Test",
        "height_cm": 178,
        "weight_class": "welterweight",
        "skill_level": "amateur_novice",
        "record_wins": 3,
    }
    r = client.patch(f"{V1}/fighters/{fid}", json=patch)
    assert r.status_code == 200
    assert r.json()["nickname"] == "Test"
    assert r.json()["height_cm"] == 178
    assert r.json()["weight_class"] == "welterweight"

    # List
    r = client.get(f"{V1}/fighters")
    assert r.status_code == 200
    assert any(f["id"] == fid for f in r.json())

    # Delete
    r = client.delete(f"{V1}/fighters/{fid}")
    assert r.status_code == 204
    assert client.get(f"{V1}/fighters/{fid}").status_code == 404


def test_v1_weigh_in_round_trip(client: TestClient) -> None:
    fid = client.post(f"{V1}/fighters", json={"name": "wi-test"}).json()["id"]

    # Empty list at start
    assert client.get(f"{V1}/fighters/{fid}/weigh-ins").json() == []

    # Create
    r = client.post(f"{V1}/fighters/{fid}/weigh-ins", json={"weight_kg": 72.5})
    assert r.status_code == 201
    wid = r.json()["id"]
    assert set(r.json().keys()) == {"id", "fighter_id", "weight_kg", "recorded_at", "notes"}

    # Mirrored onto fighter row
    assert client.get(f"{V1}/fighters/{fid}").json()["weight_kg"] == 72.5

    # Delete
    r = client.delete(f"{V1}/fighters/{fid}/weigh-ins/{wid}")
    assert r.status_code == 204


# ---------- Sessions ----------


def test_v1_session_full_lifecycle(client: TestClient) -> None:
    fid = client.post(f"{V1}/fighters", json={"name": "ses-test"}).json()["id"]

    r = client.post(f"{V1}/sessions", json={"fighter_id": fid, "source": "live_webcam"})
    assert r.status_code == 201
    sess = r.json()

    required = {
        "id",
        "fighter_id",
        "source",
        "status",
        "started_at",
        "ended_at",
        "video_path",
        "pose_parquet_path",
        "frame_count",
        "duration_ms",
        "notes",
        "failure_reason",
    }
    assert required <= set(sess.keys()), f"missing: {required - set(sess.keys())}"
    assert sess["status"] == "pending"

    sid = sess["id"]
    assert client.get(f"{V1}/sessions/{sid}").json()["id"] == sid
    assert client.get(f"{V1}/sessions/{sid}/events").json() == []

    # Filter sessions by fighter — Phase 1 surface.
    r = client.get(f"{V1}/sessions", params={"fighter_id": fid})
    assert r.status_code == 200
    assert all(s["fighter_id"] == fid for s in r.json())

    # Capture status before any start
    r = client.get(f"{V1}/sessions/{sid}/capture/status")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {
        "session_id",
        "status",
        "is_running",
        "frame_count",
        "duration_ms",
        "punch_count",
    }
    assert body["is_running"] is False

    # Stop with no running capture → 409
    assert client.post(f"{V1}/sessions/{sid}/capture/stop").status_code == 409


def test_v1_session_validation_errors_are_stable(client: TestClient) -> None:
    """Validation rejections (422 / 404 / 400) are part of the contract."""
    fid = client.post(f"{V1}/fighters", json={"name": "val-test"}).json()["id"]
    # Bad enum
    assert (
        client.post(
            f"{V1}/sessions", json={"fighter_id": fid, "source": "MARS_ROVER"}
        ).status_code
        == 422
    )
    # Empty fighter name
    assert client.post(f"{V1}/fighters", json={"name": ""}).status_code == 422
    # Unknown session
    assert client.get(f"{V1}/sessions/00000000-0000-0000-0000-000000000000").status_code == 404


def test_unversioned_alias_matches_v1_for_all_routes(client: TestClient) -> None:
    """The unversioned URL space must mirror /v1 byte-for-byte for the dashboard."""
    paths = ["/health", "/health/capabilities", "/cameras", "/fighters", "/sessions"]
    for path in paths:
        r1 = client.get(path)
        r2 = client.get(f"{V1}{path}")
        assert r1.status_code == r2.status_code, path
        assert r1.json() == r2.json(), f"diverged at {path}"

"""Pose-stream upload — persists browser landmarks as parquet."""

from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

# Import the route (which imports store models) at module level so the in-memory
# test DB registers every table before the first session fixture builds it.
from api.routes import pose as _pose  # noqa: F401


def _make_session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Pose"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def _frame(t_ms: float) -> dict:
    lms = [[0.01 * i, 0.2, 0.3, 1.0] for i in range(33)]
    return {"t_ms": t_ms, "landmarks": lms, "world_landmarks": lms}


def test_pose_upload_writes_parquet(authed_client: TestClient, tmp_path, monkeypatch) -> None:
    from api.routes import pose

    monkeypatch.setattr(pose, "_DATA_DIR", tmp_path)
    sid = _make_session(authed_client)

    r = authed_client.post(
        f"/sessions/{sid}/pose/bulk",
        json={"frames": [_frame(0), _frame(33), _frame(66)], "duration_ms": 66},
    )
    assert r.status_code == 200
    assert r.json()["frames"] == 3

    # The parquet round-trips through the standard reader.
    from capture.cv.writer import read_pose_parquet

    frames = read_pose_parquet(r.json()["path"])
    assert len(frames) == 3
    assert frames[0].world_landmarks is not None
    assert len(frames[0].landmarks) == 33


def test_pose_upload_skips_malformed_frames(
    authed_client: TestClient, tmp_path, monkeypatch
) -> None:
    from api.routes import pose

    monkeypatch.setattr(pose, "_DATA_DIR", tmp_path)
    sid = _make_session(authed_client)
    good = _frame(0)
    bad = {"t_ms": 33, "landmarks": [[0.0, 0.0, 0.0, 1.0]]}  # only 1 landmark
    r = authed_client.post(f"/sessions/{sid}/pose/bulk", json={"frames": [good, bad]})
    assert r.status_code == 200
    assert r.json()["frames"] == 1  # bad frame skipped


def test_pose_upload_all_bad_is_422(authed_client: TestClient, tmp_path, monkeypatch) -> None:
    from api.routes import pose

    monkeypatch.setattr(pose, "_DATA_DIR", tmp_path)
    sid = _make_session(authed_client)
    r = authed_client.post(
        f"/sessions/{sid}/pose/bulk",
        json={"frames": [{"t_ms": 0, "landmarks": [[0.0, 0.0, 0.0]]}]},
    )
    assert r.status_code == 422


def test_pose_upload_unknown_session_404(authed_client: TestClient) -> None:
    assert (
        authed_client.post(
            f"/sessions/{uuid4()}/pose/bulk", json={"frames": [_frame(0)]}
        ).status_code
        == 404
    )


def test_pose_upload_requires_auth(client: TestClient) -> None:
    assert client.post(f"/sessions/{uuid4()}/pose/bulk", json={"frames": []}).status_code == 401

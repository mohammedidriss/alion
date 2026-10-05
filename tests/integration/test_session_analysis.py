"""Multi-camera sessions get punch events from their cameras' pose.

The browser cameras only upload pose + clips; without this the per-round
breakdown, speed and score stayed empty for every multi-camera session.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from contracts import Landmark, PoseFrame, PunchEvent


def _frames(session_id: UUID, n: int, wrist_vis: float) -> list[PoseFrame]:
    out = []
    for i in range(n):
        lms = [Landmark(x=0.5, y=0.5, z=0.0, visibility=0.9) for _ in range(33)]
        lms[15] = Landmark(x=0.4, y=0.5, z=0.0, visibility=wrist_vis)
        lms[16] = Landmark(x=0.6, y=0.5, z=0.0, visibility=wrist_vis)
        out.append(
            PoseFrame(session_id=session_id, frame_index=i, t_ms=i * 33.3, landmarks=tuple(lms))
        )
    return out


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.routes import capture_coord
    from api.services import session_analysis

    monkeypatch.setattr(session_analysis, "POSE_DIR", tmp_path / "pose")
    monkeypatch.setattr(capture_coord, "_VIDEO_DIR", tmp_path / "clips")
    monkeypatch.setattr(capture_coord, "_STATE_DIR", tmp_path / "capture")

    # A stand-in detector: a jab every second of pose (the real heuristic needs real motion).
    def fake_detect(frames: list[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
        sid = frames[0].session_id
        return [
            PunchEvent(
                session_id=sid,
                t_ms=t,
                hand="left",
                velocity_ms=6.5,
                detected_by="heuristic",
                confidence=0.8,
            )
            for t in range(1000, int(frames[-1].t_ms), 1000)
        ]

    monkeypatch.setattr(session_analysis, "detect_punches", fake_detect)
    monkeypatch.setattr(session_analysis, "classify_punch_type", lambda *a, **k: "jab")
    yield tmp_path


def _session(client: TestClient) -> str:
    fid = client.post("/fighters", json={"name": "Mohamad", "stance": "orthodox"}).json()["id"]
    return client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]


def test_punches_come_from_the_laptop_camera_and_rerun_replaces_them(
    authed_client: TestClient, dirs: Path
) -> None:
    from capture.cv.writer import write_pose_parquet

    sid = _session(authed_client)
    (dirs / "pose").mkdir()
    (dirs / "clips").mkdir()
    # a phone that sees more, and the laptop — the laptop (front view) is preferred
    write_pose_parquet(dirs / "pose" / f"{sid}.phone1.pose.parquet", _frames(UUID(sid), 300, 0.95))
    write_pose_parquet(dirs / "pose" / f"{sid}.lap1.pose.parquet", _frames(UUID(sid), 150, 0.6))
    (dirs / "clips" / f"{sid}.lap1.json").write_text(
        json.dumps({"start_offset_ms": 10, "label": "laptop"})
    )

    assert authed_client.post(f"/sessions/{sid}/multicam/analyze").json()["punches"] == 4
    events = authed_client.get(f"/sessions/{sid}/events").json()
    assert len(events) == 4 and {e["punch_type"] for e in events} == {"jab"}
    row = authed_client.get(f"/sessions/{sid}").json()
    assert (
        row["pose_parquet_path"].endswith(f"{sid}.lap1.pose.parquet") and row["frame_count"] == 150
    )
    # idempotent
    authed_client.post(f"/sessions/{sid}/multicam/analyze")
    assert len(authed_client.get(f"/sessions/{sid}/events").json()) == 4


def test_without_a_known_laptop_the_best_seen_camera_is_used(
    authed_client: TestClient, dirs: Path
) -> None:
    from capture.cv.writer import write_pose_parquet

    sid = _session(authed_client)
    (dirs / "pose").mkdir()
    write_pose_parquet(dirs / "pose" / f"{sid}.a.pose.parquet", _frames(UUID(sid), 300, 0.2))
    write_pose_parquet(dirs / "pose" / f"{sid}.b.pose.parquet", _frames(UUID(sid), 200, 0.9))
    authed_client.post(f"/sessions/{sid}/multicam/analyze")
    assert (
        authed_client.get(f"/sessions/{sid}")
        .json()["pose_parquet_path"]
        .endswith(".b.pose.parquet")
    )


def test_stop_and_save_stores_no_camera_punches_until_the_detector_is_calibrated(
    authed_client: TestClient, dirs: Path
) -> None:
    sid = _session(authed_client)
    token = authed_client.post(f"/sessions/{sid}/multicam/join-info").json()["join_token"]
    dev = authed_client.post(
        f"/sessions/{sid}/multicam/register", json={"token": token, "label": "laptop"}
    ).json()["device_id"]
    authed_client.post(
        f"/sessions/{sid}/multicam/upload",
        data={"token": token, "device_id": dev, "start_offset_ms": "5"},
        files={"file": ("c.webm", b"\x1a\x45\xdf\xa3clip", "video/webm")},
    )
    done = authed_client.post(f"/sessions/{sid}/multicam/complete", json={"duration_ms": 4000})
    assert done.json()["status"] == "completed"
    assert authed_client.get(f"/sessions/{sid}/events").json() == []
    # the clip's sidecar keeps the camera's label for later analysis
    meta = json.loads((dirs / "clips" / f"{sid}.{dev}.json").read_text())
    assert meta == {"start_offset_ms": 5.0, "label": "laptop"}


def test_round_breakdown_counts_punches_from_the_wrist_sensors(
    authed_client: TestClient, session
) -> None:  # type: ignore[no-untyped-def]
    """No camera events → the per-round numbers come from the wrist sensors."""
    from store import HandEnum, IMUSampleRow

    sid = _session(authed_client)
    rows = []
    for hand, punches_at in (("left", [10_000, 20_000, 200_000]), ("right", [30_000])):
        for i in range(0, 220_000, 10):  # 100 Hz, rest at 1 g, a 6 g burst at each punch
            g = 6.0 if any(abs(i - p) < 40 for p in punches_at) else 1.0
            rows.append(
                IMUSampleRow(
                    session_id=UUID(sid),
                    t_ms=float(i),
                    ax_g=0.0,
                    ay_g=0.0,
                    az_g=g,
                    gx_dps=0.0,
                    gy_dps=0.0,
                    gz_dps=0.0,
                    hand=HandEnum(hand),
                )
            )
    session.add_all(rows)
    session.commit()
    out = authed_client.get(f"/sessions/{sid}/rounds_export").json()
    assert out["punch_source"] == "wrist"
    r1, r2 = out["rounds"][0], out["rounds"][1]  # 3-minute rounds
    assert (r1["punch_count"], r1["imu"]["left"], r1["imu"]["right"]) == (3, 2, 1)
    assert r1["peak_velocity_ms"] is None  # speed needs the cameras
    assert r1["imu"]["impact_score"] == round(3 * r1["imu"]["mean_peak_g"], 1)
    assert r2["punch_count"] == 1
    # no recorded duration on this session → rate over the full round
    assert r1["ppm"] == round(3 / 3.0, 1)


def test_punch_rate_uses_the_time_actually_recorded_in_the_round(
    authed_client: TestClient, session
) -> None:  # type: ignore[no-untyped-def]
    from store import HandEnum, IMUSampleRow
    from store import Session as SessionRow

    sid = _session(authed_client)
    rows = []
    for i in range(0, 60_000, 10):  # one minute recorded, a punch every 2 s on the left wrist
        g = 6.0 if i % 2000 < 40 and i > 0 else 1.0
        rows.append(
            IMUSampleRow(
                session_id=UUID(sid),
                t_ms=float(i),
                ax_g=0.0,
                ay_g=0.0,
                az_g=g,
                gx_dps=0.0,
                gy_dps=0.0,
                gz_dps=0.0,
                hand=HandEnum.LEFT,
            )
        )
    session.add_all(rows)
    row = session.get(SessionRow, UUID(sid))
    row.duration_ms = 60_000.0  # stopped one minute into a 3-minute round
    session.add(row)
    session.commit()
    r1 = authed_client.get(f"/sessions/{sid}/rounds_export").json()["rounds"][0]
    assert r1["punch_count"] == 30 and r1["ppm"] == 30.0  # per recorded minute, not per 3

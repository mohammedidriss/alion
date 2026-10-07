"""The wrist sensors and the cameras cross-check each other (services.cross_check).

A multi-camera session's per-round numbers come from both: the wrists count and
time each punch and measure its impact, the cameras confirm it and add speed.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from contracts import Hand, Landmark, PoseFrame, PunchEvent

# What each camera "detects" (the real detector needs real motion): keyed by its
# pose file's frame count, since that's all the stand-in sees.
SEEN: dict[int, list[tuple[float, Hand]]] = {}


def _frames(session_id: UUID, n: int) -> list[PoseFrame]:
    lms = tuple(Landmark(x=0.5, y=0.5, z=0.0, visibility=0.9) for _ in range(33))
    return [
        PoseFrame(session_id=session_id, frame_index=i, t_ms=i * 33.3, landmarks=lms)
        for i in range(n)
    ]


@pytest.fixture
def dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    from api.routes import capture_coord
    from api.services import cross_check, dataset_store, session_analysis

    monkeypatch.setattr(session_analysis, "POSE_DIR", tmp_path / "pose")
    monkeypatch.setattr(capture_coord, "_VIDEO_DIR", tmp_path / "clips")
    monkeypatch.setattr(capture_coord, "_STATE_DIR", tmp_path / "capture")
    monkeypatch.setattr(dataset_store, "DATASETS_DIR", tmp_path / "datasets")

    def fake_camera(frames: list[PoseFrame], *, stance: str | None = None) -> list[PunchEvent]:
        return [
            PunchEvent(
                session_id=frames[0].session_id,
                t_ms=t,
                hand=h,
                velocity_ms=2.5 + t / 100_000,
                detected_by="heuristic",
                confidence=0.6,
            )
            for t, h in SEEN[len(frames)]
        ]

    monkeypatch.setattr(cross_check, "camera_punches", fake_camera)
    (tmp_path / "pose").mkdir()
    (tmp_path / "clips").mkdir()
    yield tmp_path
    SEEN.clear()


def _imu_rows(
    session_id: UUID, punches: dict[str, list[int]], until: dict[str, int]
) -> list[object]:
    """100 Hz per wrist at rest (1 g) with a 6 g burst at each punch."""
    from store import HandEnum, IMUSampleRow

    rows: list[object] = []
    for hand, at in punches.items():
        for i in range(0, until[hand], 10):
            g = 6.0 if any(abs(i - p) < 40 for p in at) else 1.0
            rows.append(
                IMUSampleRow(
                    session_id=session_id,
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
    return rows


def _session_with_sensors(
    client: TestClient, db: Session, dirs: Path, right_until: int = 60_000
) -> str:
    from capture.cv.writer import write_pose_parquet
    from store import Session as SessionRow

    fid = client.post("/fighters", json={"name": "Mohamad", "stance": "orthodox"}).json()["id"]
    sid = client.post("/sessions", json={"fighter_id": fid, "source": "live_webcam"}).json()["id"]
    # the wrists: left at 10, 20, 30 s; right at 40 s
    db.add_all(
        _imu_rows(
            UUID(sid),
            {"left": [10_000, 20_000, 30_000], "right": [40_000]},
            {"left": 60_000, "right": right_until},
        )
    )
    row = db.get(SessionRow, UUID(sid))
    assert row is not None
    row.duration_ms = 60_000.0
    db.add(row)
    db.commit()
    # both cameras: 10, 20 and 40 s; nobody saw the 30 s punch; 50 s is camera-only
    SEEN[150] = SEEN[300] = [
        (10_040, "left"),
        (20_030, "left"),
        (40_050, "right"),
        (50_000, "right"),
    ]
    write_pose_parquet(dirs / "pose" / f"{sid}.lap1.pose.parquet", _frames(UUID(sid), 150))
    write_pose_parquet(dirs / "pose" / f"{sid}.phone1.pose.parquet", _frames(UUID(sid), 300))
    (dirs / "clips" / f"{sid}.lap1.json").write_text(json.dumps({"label": "laptop"}))
    return sid


def test_the_round_breakdown_counts_what_the_wrists_and_cameras_settle(
    authed_client: TestClient, session: Session, dirs: Path
) -> None:
    from api.services import cross_check

    sid = _session_with_sensors(authed_client, session, dirs)

    # not cross-checked yet → the wrist numbers, and the cross-check is on its way
    out = authed_client.get(f"/sessions/{sid}/rounds_export").json()
    assert out["punch_source"] == "wrist" and out["cross_check"]["status"] == "running"

    cross_check.run_now("session", UUID(sid), db=session)
    out = authed_client.get(f"/sessions/{sid}/rounds_export").json()
    assert out["punch_source"] == "fused"
    xc = out["cross_check"]
    assert xc["status"] == "ready" and xc["wrist"] is True
    # 10, 20, 40 s both saw; 30 s only the wrists (counted); 50 s only the cameras
    # while the wrists streamed (reported, not counted)
    assert (xc["counted"], xc["confirmed"], xc["wrist_only"], xc["unconfirmed"]) == (4, 3, 1, 1)
    assert xc["agreement"] == 0.75 and xc["hands"] == "unclear"
    cams = {c["device_id"]: c for c in xc["cameras"]}
    assert cams["lap1"]["label"] == "laptop" and cams["lap1"]["agreement"] == 0.75
    assert cams["lap1"]["coverage"] == 0.75

    r1 = out["rounds"][0]
    assert r1["punch_count"] == 4 and r1["ppm"] == 4.0  # one recorded minute
    b = r1["cross_check"]
    assert (b["left"], b["right"], b["confirmed"], b["unconfirmed"]) == (3, 1, 3, 1)
    # speed from the cameras (confirmed punches only), impact from the wrists
    assert b["peak_speed_ms"] == r1["peak_velocity_ms"] == 2.9
    assert b["impact_score"] is not None and b["mean_peak_g"] is not None


def test_a_wrist_sensor_dropout_is_filled_in_from_the_cameras(
    authed_client: TestClient, session: Session, dirs: Path
) -> None:
    from api.services import cross_check

    # the right sensor stopped streaming at 45 s
    sid = _session_with_sensors(authed_client, session, dirs, right_until=45_000)
    cross_check.run_now("session", UUID(sid), db=session)
    xc = authed_client.get(f"/sessions/{sid}/rounds_export").json()["cross_check"]
    assert (xc["counted"], xc["camera_only"], xc["unconfirmed"]) == (5, 1, 0)


def test_a_camera_whose_pose_stopped_early_sits_out_the_vote(
    authed_client: TestClient, session: Session, dirs: Path
) -> None:
    """A phone that went off screen sends a few frames of pose: it mustn't vote
    "no punch" for the rest of the take (it made agreement read 0%)."""
    from api.services import cross_check
    from capture.cv.writer import write_pose_parquet

    sid = _session_with_sensors(authed_client, session, dirs)
    SEEN[4] = []  # 4 frames of pose, then the page went off screen
    write_pose_parquet(dirs / "pose" / f"{sid}.k.pose.parquet", _frames(UUID(sid), 4))
    report = cross_check.run_now("session", UUID(sid), db=session)
    assert report is not None
    assert report["cameras_skipped"] == ["k"]
    assert report["totals"]["confirmed"] == 3 and report["agreement"] == 0.75


def test_a_late_camera_upload_reruns_the_cross_check(
    authed_client: TestClient, session: Session, dirs: Path
) -> None:
    from api.services import cross_check
    from capture.cv.writer import write_pose_parquet

    sid = _session_with_sensors(authed_client, session, dirs)
    cross_check.run_now("session", UUID(sid), db=session)
    assert cross_check.result("session", UUID(sid), db=session)[0] == "ready"
    SEEN[200] = [(10_000, "left")]
    write_pose_parquet(dirs / "pose" / f"{sid}.iphone.pose.parquet", _frames(UUID(sid), 200))
    assert cross_check.result("session", UUID(sid), db=session) == ("running", None)


def test_a_take_shows_agreement_per_protocol_block_and_catches_swapped_sensors(
    authed_client: TestClient, dirs: Path
) -> None:
    from api.services import cross_check, dataset_store
    from capture.cv.writer import write_pose_parquet

    did = authed_client.post("/v2/datasets", json={"name": "RQ2", "protocol": "rq2-v1"}).json()[
        "id"
    ]
    fid = authed_client.post("/fighters", json={"name": "Mohamad"}).json()["id"]
    authed_client.put(
        f"/v2/datasets/{did}/participants", json={"fighter_id": fid, "consent": "self"}
    )
    tid = authed_client.post(f"/v2/datasets/{did}/takes", json={"fighter_id": fid}).json()["id"]
    assert authed_client.get(f"/v2/takes/{tid}/cross-check").json() is None  # no pose yet

    folder = dataset_store.take_dir(UUID(tid))
    assert folder is not None
    # 40 single punches 1.5 s apart, alternating; the sensors were on the wrong wrists
    at = [3000 + 1500 * i for i in range(40)]
    sensor: list[Hand] = ["left" if i % 2 else "right" for i in range(40)]
    lines = [dataset_store.IMU_HEADER]
    for hand in ("left", "right"):
        mine = [t for t, h in zip(at, sensor, strict=True) if h == hand]
        for i in range(0, 65_000, 10):
            g = 6.0 if any(abs(i - p) < 40 for p in mine) else 1.0
            lines.append(f"{i},{hand},0,0,{g},0,0,0")
    (folder / "imu.csv").write_text("\n".join(lines) + "\n")
    dataset_store.update_take_json(folder, duration_ms=65_000.0)
    (folder / "protocol.json").write_text(
        json.dumps(
            {
                "blocks": [
                    {"key": "jab", "t_start_ms": 0, "t_end_ms": 29_000},
                    {"key": "cross", "t_start_ms": 29_000, "t_end_ms": 65_000},
                ]
            }
        )
    )
    seen = [(t + 30.0, "right" if h == "left" else "left") for t, h in zip(at, sensor, strict=True)]
    SEEN[100] = SEEN[120] = seen  # type: ignore[assignment]
    (folder / "pose").mkdir(exist_ok=True)
    write_pose_parquet(folder / "pose" / "camA.parquet", _frames(UUID(tid), 100))
    write_pose_parquet(folder / "pose" / "camB.parquet", _frames(UUID(tid), 120))

    assert authed_client.get(f"/v2/takes/{tid}/cross-check").json()["status"] == "running"
    cross_check.run_now("take", UUID(tid))
    xc = authed_client.get(f"/v2/takes/{tid}/cross-check").json()
    assert xc["status"] == "ready" and xc["hands"] == "swapped" and xc["hands_swapped"]
    assert (xc["counted"], xc["confirmed"], xc["agreement"]) == (40, 40, 1.0)
    assert [(b["key"], b["counted"], b["confirmed"]) for b in xc["blocks"]] == [
        ("jab", 18, 18),
        ("cross", 22, 22),
    ]
    assert (folder / "crosscheck.json").exists()
    assert xc["labels_swapped"] is False

    # the coach relabels with the wrists swapped: the verdict on the raw sensors
    # stands, and the card can say the labels are already corrected
    protocol = json.loads((folder / "protocol.json").read_text())
    (folder / "protocol.json").write_text(json.dumps({**protocol, "imu_hands_swapped": True}))
    xc = authed_client.get(f"/v2/takes/{tid}/cross-check").json()
    assert xc["hands"] == "swapped" and xc["labels_swapped"] is True

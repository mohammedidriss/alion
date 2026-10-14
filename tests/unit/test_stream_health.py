"""Stream health (ADR-042): each stream OK, degraded, lost or recovering."""

from __future__ import annotations

from uuid import uuid4

from api.services import stream_health as sh


def test_a_wrist_is_judged_by_rate_and_freshness() -> None:
    assert sh.wrist_state({"connected": True, "hz": 99, "last_ms_ago": 20})[0] == "ok"
    assert sh.wrist_state({"connected": True, "hz": 70, "last_ms_ago": 20}) == (
        "degraded",
        "70 readings a second",
    )
    assert sh.wrist_state({"connected": True, "hz": 99, "last_ms_ago": 900}) == (
        "degraded",
        "a gap in the data",
    )
    assert sh.wrist_state({"connected": True, "hz": 99, "last_ms_ago": 2500})[0] == "lost"
    assert sh.wrist_state({"connected": False, "hz": 0, "last_ms_ago": None}) == (
        "lost",
        "not connected",
    )


def test_the_strap_is_judged_by_beats_and_contact() -> None:
    steady = [800.0, 820.0] * 15
    assert sh.heart_state(True, 400, steady)[0] == "ok"
    noisy = list(steady)
    noisy[4] = noisy[14] = noisy[24] = 1650.0  # 3 missed beats in 30
    assert sh.heart_state(True, 400, noisy) == ("degraded", "noisy contact — wet the strap")
    assert sh.heart_state(True, 6000, steady)[0] == "lost"
    assert sh.heart_state(False, None, []) == ("lost", "not connected")


def test_a_camera_is_judged_by_when_it_was_last_heard_from() -> None:
    assert sh.camera_state({"age_ms": 300, "status": "recording"})[0] == "ok"
    assert sh.camera_state({"age_ms": 300, "status": "hidden"})[0] == "degraded"
    assert sh.camera_state({"age_ms": 3000, "status": "recording"})[0] == "degraded"
    assert sh.camera_state({"age_ms": 7000, "status": "recording"})[0] == "lost"


def test_a_stream_back_from_lost_is_recovering_until_it_has_held() -> None:
    cid = uuid4()
    assert sh._settle(cid, "wrist:left", "wrist", "ok", 0.0) == "ok"
    assert sh._settle(cid, "wrist:left", "wrist", "lost", 1.0) == "lost"
    assert sh._settle(cid, "wrist:left", "wrist", "ok", 2.0) == "recovering"
    assert sh._settle(cid, "wrist:left", "wrist", "ok", 4.0) == "recovering"
    assert sh._settle(cid, "wrist:left", "wrist", "ok", 5.5) == "ok"  # 3 s at OK
    assert sh._settle(cid, "wrist:left", "wrist", "ok", 6.0) == "ok"

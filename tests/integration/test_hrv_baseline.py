"""A resting baseline upload removes artifacts, and is refused when more than
5 % of its beats are artifacts (ADR-037)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.test_access import _session, _signup


def _csv(rrs: list[float]) -> bytes:
    return ("rr_ms\n" + "\n".join(str(r) for r in rrs)).encode()


def test_a_baseline_with_a_missed_beat_is_cleaned(client: TestClient) -> None:
    amir = _signup(client, "amir-b@alion.test", "fighter")
    sid = _session(client, amir)
    rrs = [800.0, 820.0] * 150
    rrs[100] = 1620.0  # one missed beat
    r = client.post(
        f"/sessions/{sid}/baseline/upload",
        files={"file": ("rr.csv", _csv(rrs), "text/csv")},
        headers=amir.headers,
    )
    assert r.status_code == 200, r.text
    assert abs(r.json()["baseline_rmssd_ms"] - 20.0) < 0.01


def test_a_noisy_baseline_is_refused(client: TestClient) -> None:
    amir = _signup(client, "amir-n@alion.test", "fighter")
    sid = _session(client, amir)
    rrs = [800.0, 820.0] * 50
    for i in range(3, 100, 10):  # 10 %
        rrs[i] = 1700.0
    r = client.post(
        f"/sessions/{sid}/baseline/upload",
        files={"file": ("rr.csv", _csv(rrs), "text/csv")},
        headers=amir.headers,
    )
    assert r.status_code == 422 and "more than 5 %" in r.json()["detail"]

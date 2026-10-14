"""Pupil readings as entered, kept as health data (ADR-044); the disk-encryption
status on the privacy page."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_access import _signup


def test_pupil_readings_are_health_data_kept_as_entered(client: TestClient) -> None:
    amir = _signup(client, "amir-pu@alion.test", "fighter")
    bea = _signup(client, "bea-pu@alion.test", "fighter")
    url = f"/fighters/{amir.profile_id}/pupil-readings"
    body = {
        "taken_at": "2026-10-14T12:00:00Z",
        "eye": "left",
        "npi": 4.3,
        "light_lux": 1800,
        "context": "after round 3",
    }
    r = client.post(url, json=body, headers=amir.headers)
    assert r.status_code == 201, r.text
    assert client.get(url, headers=amir.headers).json()[0]["npi"] == 4.3
    assert client.get(url, headers=bea.headers).status_code == 403  # not hers
    assert client.post(url, json={**body, "npi": None}, headers=amir.headers).status_code == 422
    assert client.post(url, json={**body, "npi": 7}, headers=amir.headers).status_code == 422
    log = client.get(f"/fighters/{amir.profile_id}/medical/access-log", headers=amir.headers).json()
    assert any("pupil-readings" in e["resource"] for e in log)  # every read logged


def test_the_privacy_page_says_whether_the_disk_is_encrypted(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.services import disk_encryption

    monkeypatch.setattr(disk_encryption, "status", lambda: "on")
    amir = _signup(client, "amir-dk@alion.test", "fighter")
    assert client.get("/v2/privacy/me", headers=amir.headers).json()["disk_encrypted"] == "on"

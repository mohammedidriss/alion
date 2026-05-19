"""End-to-end API test: HTTP → FastAPI → SQLModel → SQLite (in-memory)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from contracts import SCHEMA_VERSION


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "schema_version": SCHEMA_VERSION}


def test_fighter_crud_flow(authed_client: TestClient) -> None:
    r = authed_client.post("/fighters", json={"name": "Idriss", "stance": "orthodox"})
    assert r.status_code == 201
    fid = r.json()["id"]

    r = authed_client.get("/fighters")
    assert r.status_code == 200
    assert len(r.json()) == 1

    r = authed_client.get(f"/fighters/{fid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Idriss"

    r = authed_client.delete(f"/fighters/{fid}")
    assert r.status_code == 204

    r = authed_client.get(f"/fighters/{fid}")
    assert r.status_code == 404

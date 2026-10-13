"""Test fixtures — uses an in-memory SQLite engine, isolated per test."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from sqlmodel.pool import StaticPool


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(session: Session) -> Iterator[TestClient]:
    from api.deps import db_session
    from api.main import app

    def _override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[db_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


RESEARCHER_EMAIL = "test-coach@alion.test"


def _signed_in(client: TestClient, email: str, name: str, role: str) -> str:
    """A token for a new account that signed up (with the terms accepted)."""
    from api.services.terms import TERMS_VERSION

    resp = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "TestPass123!",
            "name": name,
            "role": role,
            "accept_terms": True,
            "terms_version": TERMS_VERSION,
        },
    )
    assert resp.status_code == 201, resp.text
    return str(resp.json()["access_token"])


def _admin_token(session: Session) -> str:
    """Nobody can sign up as admin: make the account the way an install does."""
    from api.routes.auth import _create_access_token, _hash_password
    from api.services.terms import TERMS_VERSION
    from store import User, UserRole

    user = User(
        email="test-admin@alion.test",
        password_hash=_hash_password("TestPass123!"),
        name="Test Admin",
        role=UserRole.ADMIN,
        terms_version=TERMS_VERSION,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return _create_access_token(user.id, user.role)


@pytest.fixture
def authed_client(session: Session, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A signed-in coach who is also a researcher (ADR-017) — the account that runs
    sessions for the fighters it adds (it becomes their coach) and the datasets."""
    from api.deps import db_session
    from api.main import app
    from api.services import researchers

    def _override() -> Iterator[Session]:
        yield session

    monkeypatch.setattr(researchers, "emails", lambda: {RESEARCHER_EMAIL})
    app.dependency_overrides[db_session] = _override
    with TestClient(app) as c:
        token = _signed_in(c, RESEARCHER_EMAIL, "Test Coach", "coach")
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_client(session: Session) -> Iterator[TestClient]:
    """A signed-in admin: accounts, gyms and profiles — never training data."""
    from api.deps import db_session
    from api.main import app

    def _override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[db_session] = _override
    with TestClient(app) as c:
        token = _admin_token(session)
        c.headers.update({"Authorization": f"Bearer {token}"})
        yield c
    app.dependency_overrides.clear()

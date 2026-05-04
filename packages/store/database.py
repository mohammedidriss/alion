"""SQLite engine + session factory.

Phase 8 swaps in SQLCipher for at-rest encryption. Until then, only synthetic /
self-test data may live here (see decisions/002-encryption-deferred.md).
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from common import get_settings

_settings = get_settings()
_settings.db_path.parent.mkdir(parents=True, exist_ok=True)

_engine = create_engine(
    f"sqlite:///{_settings.db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(_engine)


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session

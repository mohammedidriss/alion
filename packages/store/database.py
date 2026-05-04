"""DB engine + session factory.

The engine is built from `Settings.effective_database_url`, which is either
a Postgres URL (when `ALION_DATABASE_URL` is set) or a SQLite URL derived
from `ALION_DB_PATH`. This is the DI seam that lets the same domain run
against either backend.

Phase 8 swaps in SQLCipher for at-rest encryption (SQLite path only). Until
then, only synthetic / self-test data may live here.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from common import get_settings

_settings = get_settings()
_url = _settings.effective_database_url

if _url.startswith("sqlite"):
    _settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        _url,
        echo=False,
        connect_args={"check_same_thread": False},
    )
else:
    _engine = create_engine(_url, echo=False, pool_pre_ping=True)


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(_engine)


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session

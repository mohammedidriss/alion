"""Centralized settings, sourced from environment / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ALION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # If set, used directly (e.g. postgresql+psycopg://user:pw@host/db).
    # If unset, we build a sqlite URL from db_path. This is the DI seam that
    # lets us swap SQLite for Postgres without touching the domain or adapters.
    database_url: str | None = Field(default=None)
    db_path: Path = Field(default=Path("./data/alion.db"))
    log_level: str = Field(default="INFO")
    lm_studio_url: str = Field(default="http://localhost:1234/v1")
    llm_model: str = Field(default="llama-3.1-8b-instruct")

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.db_path}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

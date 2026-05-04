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

    db_path: Path = Field(default=Path("./data/alion.db"))
    log_level: str = Field(default="INFO")
    lm_studio_url: str = Field(default="http://localhost:1234/v1")
    llm_model: str = Field(default="llama-3.1-8b-instruct")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

"""Research accounts (ADR-017): the emails in ALION_RESEARCHERS. Only they may
open research datasets."""

from __future__ import annotations

from common import get_settings
from store import User


def emails() -> set[str]:
    return {e.strip().lower() for e in get_settings().researchers.split(",") if e.strip()}


def is_researcher(user: User | None) -> bool:
    return user is not None and user.email.lower() in emails()

"""Every piece of AI advice passes through here before anyone sees it (ADR-018).

`record` checks the answer against the blocked terms (`coach.safety`), writes an
`AdviceRecord` — what produced it (model, prompt version and hash, input hash,
platform version), what came out (and its hash), and whether it was shown,
withheld or failed — and returns that record. Callers show the advice only when
`status == "shown"`; otherwise `coach.WITHHELD` (or the failure) stands in. Rows
are only ever added, so regenerating keeps the history.
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import UUID

from sqlmodel import Session as DBSession

from coach import find_blocked
from coach.llm_client import llm_config
from store import AdviceRecord


def platform_version() -> str:
    try:
        return version("alion")
    except PackageNotFoundError:
        return "unknown"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _texts(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in _texts(v)]
    if isinstance(value, list | tuple):
        return [t for v in value for t in _texts(v)]
    return []


def record(
    db: DBSession,
    *,
    kind: str,
    system_prompt: str,
    prompt_version: str,
    user_content: str,
    output: dict[str, Any],
    failed: bool = False,
    session_id: UUID | None = None,
    fighter_id: UUID | None = None,
    payload_mode: str | None = None,
    user_id: UUID | None = None,
) -> AdviceRecord:
    """Check `output` and record it. Status: failed (the LLM didn't answer), withheld
    (it contained a blocked term), or shown."""
    blocked = [] if failed else find_blocked(*_texts(output))
    body = json.dumps(output, sort_keys=True)
    rec = AdviceRecord(
        kind=kind,
        session_id=session_id,
        fighter_id=fighter_id,
        payload_mode=payload_mode,
        status="failed" if failed else "withheld" if blocked else "shown",
        blocked_terms=json.dumps(blocked),
        output_json=body,
        model=llm_config()[2],
        prompt_version=prompt_version,
        prompt_sha256=sha256(system_prompt),
        input_sha256=sha256(user_content),
        output_sha256=sha256(body),
        platform_version=platform_version(),
        user_id=user_id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec

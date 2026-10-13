"""Every piece of AI advice passes through here before anyone sees it (ADR-018).

`record` checks the answer against the blocked terms (`coach.safety`), writes an
`AdviceRecord` — what produced it (model, prompt version and hash, input hash,
platform version), what came out (and its hash), and whether it was shown,
withheld or failed — and returns that record. Callers show the advice only when
`status == "shown"`; otherwise `coach.WITHHELD` (or the failure) stands in. Rows
are only ever added, so regenerating keeps the history; a researcher can `lock`
one as a study stimulus (ADR-019), after which it is what everyone gets.
"""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from typing import Any
from uuid import UUID

from sqlmodel import Session as DBSession
from sqlmodel import select

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


# --------------------------------------------------------------------------
# Freezing (ADR-019): a study's stimuli must not change under the raters
# --------------------------------------------------------------------------


def _for_session(db: DBSession, session_id: UUID, payload_mode: str) -> list[AdviceRecord]:
    rows = db.exec(
        select(AdviceRecord).where(
            AdviceRecord.session_id == session_id,
            AdviceRecord.kind == "corner",
            AdviceRecord.payload_mode == payload_mode,
        )
    ).all()
    return sorted(rows, key=lambda r: r.created_at)


def locked(db: DBSession, session_id: UUID, payload_mode: str) -> AdviceRecord | None:
    """The frozen advisory for this session and payload, if one was locked."""
    return next((r for r in _for_session(db, session_id, payload_mode) if r.locked), None)


def latest_shown(
    db: DBSession, session_id: UUID, payload_mode: str, prompt_version: str
) -> AdviceRecord | None:
    rows = [
        r
        for r in _for_session(db, session_id, payload_mode)
        if r.status == "shown" and r.prompt_version == prompt_version
    ]
    return rows[-1] if rows else None


def lock(db: DBSession, rec: AdviceRecord) -> AdviceRecord:
    """Freeze an advisory as a study stimulus — for good: it is what everyone gets
    from now on, and regenerating it is refused."""
    rec.locked = True
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def history(db: DBSession, session_id: UUID) -> list[AdviceRecord]:
    rows = db.exec(select(AdviceRecord).where(AdviceRecord.session_id == session_id)).all()
    return sorted(rows, key=lambda r: r.created_at)

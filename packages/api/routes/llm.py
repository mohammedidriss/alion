"""The coach's LLM: which setup advice uses — local or remote — which of its
models, and switching (ADR-021, ADR-049). For researchers and admins.

    GET  /v2/llm          both setups: address, models installed, the one in use, …
    PUT  /v2/llm          {"choice": "local" | "remote", "model"?} — from the next request on
    POST /v2/llm/test     {"choice", "model"?} — one tiny request: does it answer, how fast
    POST /v2/llm/trial    {"choice", "model", "session_id", "after_round"} — that model
                          phrases one round's rest cards: how long, and what the
                          verifier passed. Nothing is shown to a coach or recorded as
                          advice; the session must be one the caller may read.
"""

from __future__ import annotations

import time
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import Session as DBSession

from api import access
from api.deps import db_session, punch_event_repo, session_repo
from coach.llm_client import installed_models, llm_config, ping
from common import llm_setups
from store import PunchEventRepo, SessionRepo

TRIAL_TIMEOUT_S = 90.0  # a slow model is still timed; the rest minute's limit is reported

router = APIRouter(prefix="/v2/llm", tags=["llm"])


def require_researcher_or_admin(
    viewer: access.Viewer = Depends(access.require_viewer),
) -> access.Viewer:
    if not (viewer.researcher or viewer.admin):
        raise HTTPException(
            status_code=403, detail="Only researchers and admins choose the AI model"
        )
    return viewer


class SetupOut(BaseModel):
    name: str  # local | remote
    label: str
    url: str
    model: str
    active: bool
    on_own_network: bool  # a public address is refused (advice data stays local)
    reachable: bool  # its server answered
    model_installed: bool  # …and offers this model
    models: list[str] = []  # every model it offers (empty when it doesn't answer)
    configured_model: str = ""  # the one .env names


class LlmOut(BaseModel):
    active: str | None  # None: no setups configured — the single ALION_LLM_URL is used
    in_use: dict[str, str]  # what advice uses right now: url, model
    setups: list[SetupOut]


class ChoiceIn(BaseModel):
    choice: Literal["local", "remote"]
    model: str | None = None  # one of the models installed there


class TrialIn(BaseModel):
    choice: Literal["local", "remote"]
    model: str
    session_id: UUID
    after_round: int = Field(ge=1)


def _setup(choice: str, model: str | None) -> llm_setups.LlmSetup:
    """The setup, refused when it isn't configured or allowed, or when it answers and
    doesn't have the model."""
    setup = llm_setups.setups().get(choice)
    if setup is None:
        raise HTTPException(status_code=404, detail=f"no '{choice}' AI is configured")
    if not setup.allowed:
        raise HTTPException(status_code=409, detail=f"{setup.url} isn't on your own network")
    if model:
        models = installed_models(setup.url, setup.api_key)
        if models is None:
            raise HTTPException(status_code=409, detail=f"{setup.label} isn't answering")
        if model not in models:
            raise HTTPException(status_code=409, detail=f"{model} isn't installed on {setup.label}")
    return setup


def _status() -> LlmOut:
    active = llm_setups.active_name()
    out = []
    for s in llm_setups.setups().values():
        models = installed_models(s.url, s.api_key)
        out.append(
            SetupOut(
                name=s.name,
                label=s.label,
                url=s.url,
                model=s.model,
                active=s.name == active,
                on_own_network=s.on_own_network,
                reachable=models is not None,
                model_installed=models is not None and s.model in models,
                models=sorted(models or []),
                configured_model=s.configured_model,
            )
        )
    url, _, model = llm_config()
    return LlmOut(active=active, in_use={"url": url, "model": model}, setups=out)


@router.get("", response_model=LlmOut)
def get_llm(_: access.Viewer = Depends(require_researcher_or_admin)) -> LlmOut:
    return _status()


@router.put("", response_model=LlmOut)
def choose_llm(body: ChoiceIn, _: access.Viewer = Depends(require_researcher_or_admin)) -> LlmOut:
    """Switch the AI that advice uses — from the next request on, no restart. Every
    advisory records which model produced it (ADR-018)."""
    _setup(body.choice, body.model)
    try:
        llm_setups.choose(body.choice, body.model)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    return _status()


@router.post("/test", response_model=dict)
async def test_llm(
    body: ChoiceIn, _: access.Viewer = Depends(require_researcher_or_admin)
) -> dict[str, Any]:
    setup = llm_setups.setups().get(body.choice)
    if setup is None:
        raise HTTPException(status_code=404, detail=f"no '{body.choice}' AI is configured")
    return await ping(setup.url, setup.api_key, body.model or setup.model)


@router.post("/trial", response_model=dict)
async def trial(
    body: TrialIn,
    viewer: access.Viewer = Depends(require_researcher_or_admin),
    sessions: SessionRepo = Depends(session_repo),
    events: PunchEventRepo = Depends(punch_event_repo),
    db: DBSession = Depends(db_session),
) -> dict[str, Any]:
    """One model phrases one round's rest cards, exactly as in the rest minute (same
    facts, prompt and verifier), but with no time limit to speak of: how long it
    took, how many cards it wrote, which passed every gate and why the others
    didn't. For comparing models (ADR-049) — never shown to a coach, never recorded
    as advice."""
    from api.routes import rest_cards as rc
    from api.services import advice_gate, rest_cards
    from coach import find_blocked

    setup = _setup(body.choice, body.model)
    row = rc._gate(db, body.session_id)  # 404, and the coach-only study condition
    viewer.require(row.fighter_id, access.Level.TRAINING)
    ex, facts = rc._ledger(body.session_id, body.after_round, False, sessions, events, db)
    t = time.perf_counter()
    _, output, verdicts, shown, _ = await rc.phrase(
        ex,
        body.after_round,
        facts,
        target=(setup.url, setup.api_key, body.model),
        timeout_s=TRIAL_TIMEOUT_S,
    )
    seconds = round(time.perf_counter() - t, 1)
    blocked = find_blocked(*advice_gate._texts(output)) if output else []
    written = output.get("cards") if isinstance(output, dict) else None
    return {
        "choice": body.choice,
        "label": setup.label,
        "model": body.model,
        "after_round": body.after_round,
        "round_count": ex.round_count,
        "facts": len(facts),
        "seconds": seconds,
        "answered": output is not None,
        "in_time": output is not None and seconds <= rc.PHRASE_TIMEOUT_S,
        "written": len(written) if isinstance(written, list) else 0,
        # a blocked term anywhere withholds every model card, as in the rest minute
        "passed": 0 if blocked else sum(1 for v in verdicts if v["ok"]),
        "blocked_terms": blocked,
        "verdicts": verdicts,
        "cards": [c.model_dump() for c in (rest_cards.template_cards(facts) if blocked else shown)],
    }

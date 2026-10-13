"""The coach's LLM: which setup advice uses — local or remote — and switching it
(ADR-021). For researchers and admins.

    GET  /v2/llm          both setups: address, model, reachable, model installed, in use
    PUT  /v2/llm          {"choice": "local" | "remote"} — used from the next request on
    POST /v2/llm/test     {"choice": …} — one tiny request: does it answer, how fast
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api import access
from coach.llm_client import installed_models, llm_config, ping
from common import llm_setups

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


class LlmOut(BaseModel):
    active: str | None  # None: no setups configured — the single ALION_LLM_URL is used
    in_use: dict[str, str]  # what advice uses right now: url, model
    setups: list[SetupOut]


class ChoiceIn(BaseModel):
    choice: Literal["local", "remote"]


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
    try:
        llm_setups.choose(body.choice)
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
    return await ping(setup.url, setup.api_key, setup.model)

"""OpenAI-compatible client for the coach's LLM — Ollama, LM Studio or similar,
on this machine or another one on your network (ADR-021)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel

from common import get_settings, llm_setups

# Where coach inference goes. Read on every call, in this order:
#   1. COACH_BASE_URL / COACH_API_KEY / COACH_MODEL in the environment;
#   2. the setup the researcher picked — "local" or "remote" (common.llm_setups,
#      ADR-021) — switchable at runtime, no restart;
#   3. the project's .env — ALION_LLM_URL (or the older ALION_LM_STUDIO_URL),
#      ALION_LLM_API_KEY, ALION_LLM_MODEL (common.settings);
#   4. the generic OPENAI_BASE_URL / OPENAI_API_KEY;
#   5. local LM Studio.
# Whatever it is, it must be on your own network unless ALION_LLM_ALLOW_PUBLIC.
# Alion-specific names come first so a developer's existing OPENAI_* (e.g. an
# Ollama dev setup) doesn't silently redirect coach inference.
LM_STUDIO_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "google/gemma-4-e4b"


def llm_config() -> tuple[str, str, str]:
    """(base URL, API key, model) of the LLM that coach advice uses."""
    s = get_settings()
    setup = llm_setups.active()
    url = os.getenv("COACH_BASE_URL") or (setup.url if setup else s.llm_url)
    key = os.getenv("COACH_API_KEY") or (setup.api_key if setup else s.llm_api_key)
    model = os.getenv("COACH_MODEL") or (setup.model if setup else s.llm_model) or DEFAULT_MODEL
    if not url:
        url = os.getenv("OPENAI_BASE_URL") or LM_STUDIO_URL
        # An Ollama OPENAI_BASE_URL with the LM Studio default model is a
        # polluted shell, never a real config — stay on LM Studio.
        if "11434" in url and model == DEFAULT_MODEL:
            url = LM_STUDIO_URL
    key = key or os.getenv("OPENAI_API_KEY") or "lm-studio"
    return url, key, model


class LlmNotAllowedError(RuntimeError):
    """The LLM is on a public address — advice data stays on your own network."""


def _client(url: str, key: str) -> AsyncOpenAI:
    if not (llm_setups.is_own_network(url) or get_settings().llm_allow_public):
        raise LlmNotAllowedError(
            f"{url} isn't on your own network — session data stays local (ADR-021)"
        )
    return AsyncOpenAI(base_url=url, api_key=key)


# NOTE: a module-level AsyncOpenAI client used to live here. We saw a
# repro where the long-lived client kept returning "model not found"
# 404s from LM Studio even though fresh processes hitting the same
# endpoint succeeded — almost certainly a stale connection / cached
# state inside httpx. Creating the client per call is cheap on
# localhost and makes LM Studio's just-in-time loading reliable.


class CoachAdvice(BaseModel):
    summary: str
    action_items: list[str]


async def generate_corner_advice(system_prompt: str, session_data_json: str) -> CoachAdvice:
    """Generate corner advice from session performance data.

    Tries to parse the JSON output from the LLM. If the LLM failed to produce valid JSON,
    it falls back to a raw text summary.
    """
    import asyncio

    async def _call() -> Any:
        # Fresh client per call — avoids the stale-connection 404s
        # described above. AsyncOpenAI is cheap to construct.
        url, key, model = llm_config()
        c = _client(url, key)
        return await c.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": session_data_json},
            ],
            temperature=0.5,
            max_tokens=800,
        )

    # Retry once on transient errors. The most common is LM Studio
    # returning 404 'model not found' when the model is unloaded; on
    # the retry it just-in-time loads. We sleep briefly to give it
    # time to come up.
    completion = None
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            completion = await _call()
            break
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = (
                "404" in msg
                or "not found" in msg
                or "service unavailable" in msg
                or "connection error" in msg
            )
            if attempt == 0 and transient:
                await asyncio.sleep(2.0)
                continue
            break
    if completion is None:
        return CoachAdvice(
            summary=f"Failed to connect to LLM ({llm_config()[2]} at {llm_config()[0]}): {last_err}",
            action_items=[],
        )

    content = completion.choices[0].message.content or "{}"
    return _parse_advice(content)


def _parse_advice(content: str) -> CoachAdvice:
    """Robust JSON extraction.

    Small open-source models occasionally:
    - wrap in ```json``` fences,
    - return trailing commentary,
    - nest the real JSON inside the `summary` field as a string.
    Try the obvious parse first, then a brace-balanced extract, then
    grep the inner JSON. Last resort: surface the raw text.
    """
    s = content.strip()
    # 1. Strip markdown fences.
    s = re.sub(r"^```(?:json)?\s*", "", s)
    s = re.sub(r"\s*```$", "", s)
    # 2. Brace-balanced extract — first {...} that parses.
    candidate = _first_balanced_object(s) or s
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # 3. Try to greedy-find a "summary" key in the raw text.
        m = re.search(r'"summary"\s*:\s*"([^"]+)"', content, re.S)
        items = re.findall(r'"([^"]{6,160})"\s*[,\]]', content)
        return CoachAdvice(
            summary=m.group(1) if m else content[:300].strip(),
            action_items=items[:3] if m else [],
        )
    # 4. Sometimes the model nests another JSON inside summary.
    summary = data.get("summary")
    actions = data.get("action_items") or []
    if isinstance(summary, str) and summary.lstrip().startswith("{"):
        try:
            inner = json.loads(_first_balanced_object(summary) or summary)
            summary = inner.get("summary", summary)
            if not actions:
                actions = inner.get("action_items", [])
        except json.JSONDecodeError:
            pass
    return CoachAdvice(
        summary=summary or "No summary provided.",
        action_items=list(actions),
    )


async def generate_raw(system_prompt: str, user_content: str) -> str:
    """Send a prompt to the LLM and return the raw response text.

    No parsing — the caller handles structured extraction. Uses the same
    retry logic as generate_corner_advice.
    """
    import asyncio

    async def _call() -> Any:
        url, key, model = llm_config()
        c = _client(url, key)
        return await c.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.5,
            max_tokens=1200,
        )

    last_err: Exception | None = None
    for attempt in range(2):
        try:
            completion = await _call()
            return completion.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            transient = "404" in msg or "not found" in msg or "connection error" in msg
            if attempt == 0 and transient:
                await asyncio.sleep(2.0)
                continue
            break
    return f'{{"error": "LLM error: {last_err}"}}'


async def generate_json(
    system_prompt: str, user_content: str, schema: dict[str, Any], *, timeout_s: float = 12.0
) -> dict[str, Any] | None:
    """A JSON object shaped by `schema`, or None on any failure or timeout.

    Asks for structured output (OpenAI-style `json_schema`, which Ollama and LM
    Studio constrain the decoding to); a server without it gets the schema in the
    prompt and the first balanced object is parsed. Callers must verify the
    content: the schema fixes the shape, not the truth (ADR-041)."""
    import asyncio

    url, key, model = llm_config()
    c = _client(url, key)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    async def _call(structured: bool) -> str:
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 600,
            "timeout": timeout_s,
        }
        if structured:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "cards", "schema": schema, "strict": True},
            }
        completion = await c.chat.completions.create(**kwargs)
        return completion.choices[0].message.content or ""

    for structured in (True, False):
        try:
            text = await asyncio.wait_for(_call(structured), timeout=timeout_s)
        except Exception as e:
            # Too slow: no second try (the cards are already on screen). Anything
            # else may be a server without structured output — ask again plainly.
            if isinstance(e, TimeoutError) or "timeout" in type(e).__name__.lower():
                return None
            continue
        body = _first_balanced_object(text.strip())
        if body is None:
            continue
        try:
            data = json.loads(body)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _first_balanced_object(s: str) -> str | None:
    """Return the first {...} substring with balanced braces, or None."""
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return None


async def ping(url: str, key: str, model: str) -> dict[str, Any]:
    """One tiny request to a setup — is it there, does it answer, how fast?
    {ok, seconds, reply | error}. The first call may include loading the model."""
    import time

    t = time.time()
    try:
        c = _client(url, key)
        done = await c.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with one word: ready"}],
            max_tokens=10,
            temperature=0,
        )
        reply = (done.choices[0].message.content or "").strip()
        return {"ok": True, "seconds": round(time.time() - t, 1), "reply": reply[:60]}
    except Exception as e:  # reported to the researcher, not raised
        return {"ok": False, "seconds": round(time.time() - t, 1), "error": str(e)[:200]}


def installed_models(url: str, key: str, timeout: float = 2.5) -> list[str] | None:
    """The models an OpenAI-compatible server offers (GET /models), or None if it
    doesn't answer."""
    import httpx

    if not (llm_setups.is_own_network(url) or get_settings().llm_allow_public):
        return None
    try:
        r = httpx.get(
            url.rstrip("/") + "/models", headers={"Authorization": f"Bearer {key}"}, timeout=timeout
        )
        r.raise_for_status()
        return [str(m.get("id")) for m in r.json().get("data", [])]
    except (httpx.HTTPError, ValueError, AttributeError):
        return None

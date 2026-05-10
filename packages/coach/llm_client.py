"""OpenAI-compatible client for LM Studio / OpenAI."""

from __future__ import annotations

import json
import os
import re

from openai import AsyncOpenAI
from pydantic import BaseModel

# Default to local LM Studio
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://localhost:1234/v1")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "lm-studio")
MODEL = os.getenv("COACH_MODEL", "google/gemma-4-e4b")

client = AsyncOpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)


class CoachAdvice(BaseModel):
    summary: str
    action_items: list[str]


async def generate_corner_advice(system_prompt: str, session_data_json: str) -> CoachAdvice:
    """Generate corner advice from session performance data.

    Tries to parse the JSON output from the LLM. If the LLM failed to produce valid JSON,
    it falls back to a raw text summary.
    """
    import asyncio

    async def _call() -> object:
        return await client.chat.completions.create(
            model=MODEL,
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
            summary=f"Failed to connect to LLM ({MODEL}): {last_err}",
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

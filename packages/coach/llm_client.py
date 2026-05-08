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
MODEL = os.getenv("COACH_MODEL", "meta-llama-3.1-8b-instruct")

client = AsyncOpenAI(base_url=OPENAI_BASE_URL, api_key=OPENAI_API_KEY)


class CoachAdvice(BaseModel):
    summary: str
    action_items: list[str]


async def generate_corner_advice(system_prompt: str, session_data_json: str) -> CoachAdvice:
    """Generate corner advice from session performance data.

    Tries to parse the JSON output from the LLM. If the LLM failed to produce valid JSON,
    it falls back to a raw text summary.
    """
    try:
        completion = await client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": session_data_json},
            ],
            temperature=0.7,
            max_tokens=500,
        )
    except Exception as e:
        return CoachAdvice(
            summary=f"Failed to connect to LLM ({MODEL}): {e}",
            action_items=[],
        )

    content = completion.choices[0].message.content or "{}"

    # Strip out markdown code blocks if the model wrapped the JSON
    content = re.sub(r"^```json\s*", "", content)
    content = re.sub(r"^```\s*", "", content)
    content = re.sub(r"\s*```$", "", content)

    try:
        data = json.loads(content)
        return CoachAdvice(
            summary=data.get("summary", "No summary provided."),
            action_items=data.get("action_items", []),
        )
    except json.JSONDecodeError:
        return CoachAdvice(
            summary=content.strip(),
            action_items=[],
        )

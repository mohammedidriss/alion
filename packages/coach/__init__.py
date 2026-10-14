"""coach — phase-gated module. See Combat_Intel_Build_Brief.md §5 for when this gets implemented.

Constraint: depends only on `contracts` and `common`. Never imports from sibling feature modules.
"""

from .llm_client import CoachAdvice, generate_corner_advice, generate_raw
from .prompts import (
    CORNER_ADVICE_SYSTEM_PROMPT,
    FIGHTER_OBSERVATION_SYSTEM_PROMPT,
    WEIGHT_ANALYSIS_SYSTEM_PROMPT,
)
from .safety import WITHHELD, find_blocked

# Bumping this string invalidates every cached advice row. The /advice
# route stores it on each cache entry; a mismatch on lookup forces a
# fresh generation. Bump whenever the prompt or LLM changes in a way
# that should reset the RQ1 rater dataset.
PROMPT_VERSION = "v4"  # v4: body data only as training, no medicines or water cuts (ADR-039)

__all__ = [
    "CORNER_ADVICE_SYSTEM_PROMPT",
    "FIGHTER_OBSERVATION_SYSTEM_PROMPT",
    "PROMPT_VERSION",
    "WEIGHT_ANALYSIS_SYSTEM_PROMPT",
    "WITHHELD",
    "CoachAdvice",
    "find_blocked",
    "generate_corner_advice",
    "generate_raw",
]

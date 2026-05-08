"""coach — phase-gated module. See Combat_Intel_Build_Brief.md §5 for when this gets implemented.

Constraint: depends only on `contracts` and `common`. Never imports from sibling feature modules.
"""

from .llm_client import CoachAdvice, generate_corner_advice
from .prompts import CORNER_ADVICE_SYSTEM_PROMPT

__all__ = [
    "CORNER_ADVICE_SYSTEM_PROMPT",
    "CoachAdvice",
    "generate_corner_advice",
]

"""Advice safety (ADR-018): non-binding training advice, never medical.

Two layers. The prompts carry `SAFETY_RULES`, so the model is told what it must
not do. And every answer is checked before anyone sees it: if it contains a
term from `blocked_terms.txt` (diagnoses and conditions, fitness verdicts,
stoppage and clearance) it is withheld — replaced by `WITHHELD`, with the terms
that tripped it, for the caller to log. A false alarm costs one withheld
advisory; a missed one could read as a medical judgement.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

BLOCKED_TERMS_FILE = Path(__file__).with_name("blocked_terms.txt")

SAFETY_RULES = """Safety rules — these override everything else:
- You give non-binding training advice to a person (a coach or the fighter), who decides. Word every point as a suggestion ("consider…", "try…"), never as an order or a verdict.
- Never diagnose, name or suggest any injury, illness or medical condition.
- Never say whether anyone is fit, safe or unsafe to train, spar, fight or continue. Never recommend stopping, ending or continuing a round or bout, and never give or imply medical clearance.
- If something in the data might be a health matter, say only: "Worth checking with the team's medical staff." Nothing more about it.
- Stay on training: technique, pacing, volume, recovery habits, preparation."""

WITHHELD = (
    "This advice was withheld: it touched on medical or safety judgements, which the "
    "platform must not make. A person should review the data."
)


@lru_cache(maxsize=1)
def blocked_terms() -> tuple[str, ...]:
    lines = BLOCKED_TERMS_FILE.read_text().splitlines()
    return tuple(t.strip().lower() for t in lines if t.strip() and not t.lstrip().startswith("#"))


@lru_cache(maxsize=1)
def _patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    return tuple(
        (t, re.compile(rf"(?<![^\W_]){re.escape(t)}(?![^\W_])", re.IGNORECASE))
        for t in blocked_terms()
    )


def find_blocked(*texts: str) -> list[str]:
    """The blocked terms anywhere in `texts` (whole words, any case), in list order."""
    joined = "\n".join(texts)
    return [t for t, pattern in _patterns() if pattern.search(joined)]

"""Advice safety (ADR-018): non-binding training advice, never medical.

Two layers. The prompts carry `SAFETY_RULES`, so the model is told what it must
not do. And every answer is checked before anyone sees it: if it contains a
term from `blocked_terms.txt` (diagnoses and conditions, symptoms, medicines,
weight cutting by dehydration, fitness verdicts, stoppage and clearance) or a
phrase putting an organ next to a problem ("heart problem", "brain damage") it
is withheld — replaced by `WITHHELD`, with what tripped it, for the caller to
log. The check runs again every time stored advice is shown (ADR-039), so a term
added to the file also stops advice written before it. A false alarm costs one
withheld advisory; a missed one could read as a medical judgement.
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
- Read heart rate, HRV, weight, punch force and every other number only as training load, effort, pacing, recovery or technique — never as a sign of a health problem, and never comment on the heart, brain, head or any organ.
- Never mention medicines, painkillers or supplements as a treatment, and never suggest losing weight by dehydration, sauna or sweat suits, water cutting, diuretics, laxatives or not eating.
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


# An organ next to a problem within a few words: "heart problem", "irregular heart
# rhythm", "damage to the brain". Organs only — "head movement is an issue" is
# coaching, so the head isn't one of them.
_ORGAN = r"(?:heart|brain|lungs?|kidneys?|blood pressure|nervous system)"
_PROBLEM = r"(?:problems?|issues?|damage|conditions?|abnormal(?:ity|ities)?|irregular(?:ity)?|disease|trauma|failure)"
ORGAN_PROBLEM = "organ + problem"
_ORGAN_PATTERNS = (
    re.compile(rf"\b{_ORGAN}\b(?:\W+\w+){{0,4}}?\W+{_PROBLEM}\b", re.IGNORECASE),
    re.compile(rf"\b{_PROBLEM}\b(?:\W+\w+){{0,4}}?\W+{_ORGAN}\b", re.IGNORECASE),
)


def find_blocked(*texts: str) -> list[str]:
    """What makes `texts` medical: the blocked terms in them (whole words, any case,
    in list order), then "organ + problem" if a phrase pairs the two."""
    joined = "\n".join(texts)
    found = [t for t, pattern in _patterns() if pattern.search(joined)]
    if any(p.search(joined) for p in _ORGAN_PATTERNS):
        found.append(ORGAN_PROBLEM)
    return found

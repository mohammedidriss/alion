"""The claim verifier (ADR-041): a model may phrase a rest card, never source it.

Every card a model writes is checked against the facts ledger it was given, gate
by gate; the first gate it fails drops it, and the slot keeps its template card.
Nothing is repaired. The gates:

1. shape — a known slot, short headline and detail, at least one citation;
2. citations — every cited fact exists, and fits the slot (recovery cites heart
   facts; the tactical slots don't);
3. numbers — every number written is one a cited fact holds (its value, total,
   previous value, round or seconds), as the ledger writes it;
4. rounds and hands — "round N" and left / right / lead / rear match what the
   cited facts are about;
5. direction — up / down words (more, fewer, faster, slower…) agree with a cited
   fact's direction;
6. evidence — no "landed", "blocked", "hit": the sensors say thrown;
7. inference — no guesses about the fighter's mind or body ("suggests
   confidence", "tired", "struggling"): the facts are counts and rates;
8. quality — every cited fact at 0.5 or better;
9. safety — the blocked-term check (ADR-018, ADR-039).

Facts are plain dicts here (`coach` doesn't import the API); the ledger lives in
`api.services.rest_cards`.
"""

from __future__ import annotations

import re
from typing import Any

from coach.safety import find_blocked

SLOTS = ("opportunity", "warning", "recovery")
HEART_KINDS = {"heart", "rest"}
MAX_HEADLINE_WORDS = 8
MAX_DETAIL_WORDS = 16
MIN_QUALITY = 0.5

_NUMBER = re.compile(r"(?<![\w.])[-−+]?(\d+(?:\.\d+)?)")
_NUMBER_WORDS = re.compile(
    r"\b(zero|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred|half|double|twice|triple)\b",
    re.IGNORECASE,
)
_ROUND = re.compile(r"\b(?:round|r)\s*(\d+)\b", re.IGNORECASE)
_HANDS = re.compile(r"\b(left|right|lead|rear)\b", re.IGNORECASE)
_UP = re.compile(
    r"\b(up|more|higher|faster|rising|rose|increased?|climbed|busier|quicker)\b", re.IGNORECASE
)
_DOWN = re.compile(
    r"\b(down|fewer|less|lower|slower|dropp?ed|dropping|fell|falling|decreased?|fading|faded|quieter)\b",
    re.IGNORECASE,
)
_EVIDENCE = re.compile(
    r"\b(land(?:ed|ing|s)?|block(?:ed|ing|s)?|connect(?:ed|ing|s)?|hit(?:s|ting)?|scor(?:ed|ing|es)|"
    r"clean shots?|knock(?:ed|down)?)\b",
    re.IGNORECASE,
)


_INFERENCE = re.compile(
    r"\b(suggest(?:s|ing|ed)?|indicat(?:es|ing|ed)|impl(?:y|ies|ied)|means|likely|probably|perhaps|"
    r"maybe|confiden(?:ce|t)|tired(?:ness)?|fatigu(?:e|ed)|exhaust(?:ed|ion)|nervous|anxious|"
    r"mental(?:ly)?|motivat(?:ed|ion)|struggl(?:e|es|ing)|dominat(?:e|es|ing|ed)|winning|losing|"
    r"gassed|hurt|rattled|frustrat(?:ed|ion))\b",
    re.IGNORECASE,
)


def _fmt(x: float) -> str:
    r = round(float(x), 1)
    return str(int(r)) if r == int(r) else f"{r:.1f}"


def _allowed_numbers(fact: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for key in ("value", "of", "previous", "round", "previous_round"):
        v = fact.get(key)
        if isinstance(v, int | float):
            out.add(_fmt(v))
            out.add(_fmt(abs(v)))
            out.add(str(round(v)))
    return out


def _words(text: str) -> int:
    return len(text.split())


def check_card(card: dict[str, Any], facts: dict[str, dict[str, Any]]) -> str | None:
    """None when the card passes; otherwise the gate it failed, and why."""
    slot = card.get("slot")
    headline = str(card.get("headline") or "").strip()
    detail = str(card.get("detail") or "").strip()
    cites = card.get("cites") or []
    # 1. shape
    if slot not in SLOTS:
        return "shape: unknown slot"
    if not headline or _words(headline) > MAX_HEADLINE_WORDS or _words(detail) > MAX_DETAIL_WORDS:
        return "shape: too long or empty"
    if not isinstance(cites, list) or not cites:
        return "citations: none"
    # 2. citations exist and fit the slot
    cited = [facts.get(str(c)) for c in cites]
    if any(f is None for f in cited):
        return "citations: unknown fact"
    fs = [f for f in cited if f is not None]
    heart = [f["kind"] in HEART_KINDS for f in fs]
    if slot == "recovery" and not all(heart):
        return "citations: recovery must cite heart facts"
    if slot != "recovery" and any(heart):
        return "citations: tactical cards can't cite heart facts"
    text = f"{headline}\n{detail}"
    # 3. numbers
    allowed = set().union(*(_allowed_numbers(f) for f in fs))
    for m in _NUMBER.finditer(text):
        if _fmt(float(m.group(1))) not in allowed:
            return f"numbers: {m.group(1)} isn't in the cited facts"
    if _NUMBER_WORDS.search(text):
        return "numbers: written-out number"
    # 4. rounds and hands
    rounds = {r for f in fs for r in (f.get("round"), f.get("previous_round")) if r is not None}
    for m in _ROUND.finditer(text):
        if int(m.group(1)) not in rounds:
            return f"rounds: round {m.group(1)} isn't what the facts are about"
    hands = {str(f["hand"]).lower() for f in fs if f.get("hand")}
    for m in _HANDS.finditer(text):
        if m.group(1).lower() not in hands:
            return f"hands: {m.group(1)} isn't in the cited facts"
    # 5. direction
    directions = {f.get("direction") for f in fs}
    if _UP.search(text) and "up" not in directions:
        return "direction: says up, the facts don't"
    if _DOWN.search(text) and "down" not in directions:
        return "direction: says down, the facts don't"
    # 6. evidence
    if _EVIDENCE.search(text):
        return "evidence: the sensors say thrown, not landed or blocked"
    # 7. inference
    guess = _INFERENCE.search(text)
    if guess:
        return f"inference: '{guess.group(1)}' is a guess the facts don't make"
    # 8. quality
    if any(float(f.get("quality", 0)) < MIN_QUALITY for f in fs):
        return "quality: a cited fact is too weak"
    # 9. safety
    blocked = find_blocked(text)
    if blocked:
        return f"safety: {', '.join(blocked)}"
    return None


def verify_cards(
    output: Any, facts: list[dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """(the cards that passed, by slot — at most one each; a verdict per card)."""
    by_id = {str(f["id"]): f for f in facts}
    cards = output.get("cards") if isinstance(output, dict) else None
    if not isinstance(cards, list):
        return {}, [{"slot": None, "ok": False, "gate": "shape: no cards"}]
    passed: dict[str, dict[str, Any]] = {}
    verdicts: list[dict[str, Any]] = []
    for card in cards:
        if not isinstance(card, dict):
            verdicts.append({"slot": None, "ok": False, "gate": "shape: not an object"})
            continue
        gate = check_card(card, by_id)
        slot = card.get("slot")
        if gate is None and slot in passed:
            gate = "shape: second card for the slot"
        verdicts.append({"slot": slot, "ok": gate is None, "gate": gate})
        if gate is None:
            passed[str(slot)] = card
    return passed, verdicts

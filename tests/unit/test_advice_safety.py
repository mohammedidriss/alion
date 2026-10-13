"""Advice safety (coach.safety, ADR-018): the blocked-term check every AI answer
passes, and the safety rules every prompt carries."""

from __future__ import annotations

from coach import (
    CORNER_ADVICE_SYSTEM_PROMPT,
    FIGHTER_OBSERVATION_SYSTEM_PROMPT,
    WEIGHT_ANALYSIS_SYSTEM_PROMPT,
    find_blocked,
)
from coach.safety import SAFETY_RULES, blocked_terms


def test_medical_words_fitness_verdicts_and_stoppage_are_caught_in_any_case() -> None:
    assert find_blocked("Possible CONCUSSION — sit him down") == ["concussion"]
    assert "unsafe" in find_blocked("He looks unsafe to continue")
    assert "stop the fight" in find_blocked("Tell the referee to stop the fight")
    assert "medical clearance" in find_blocked("needs medical clearance first")
    assert "dehydration" in find_blocked("signs of dehydration")


def test_whole_words_only_and_training_advice_passes() -> None:
    assert find_blocked("Double the jab, keep the chin tucked, pace the third round") == []
    assert find_blocked("Worth checking with the team's medical staff.") == []
    assert find_blocked("an unsafeguarded stance") == []  # not the word "unsafe"


def test_every_prompt_carries_the_safety_rules_and_none_asks_for_a_medical_judgement() -> None:
    for prompt in (
        CORNER_ADVICE_SYSTEM_PROMPT,
        FIGHTER_OBSERVATION_SYSTEM_PROMPT,
        WEIGHT_ANALYSIS_SYSTEM_PROMPT,
    ):
        assert prompt.endswith(SAFETY_RULES)
        assert find_blocked(prompt.replace(SAFETY_RULES, "")) == []
    assert "name" not in FIGHTER_OBSERVATION_SYSTEM_PROMPT.split("Your job")[0].split("fighter:")[1]


def test_the_blocked_terms_come_from_the_editable_file() -> None:
    terms = blocked_terms()
    assert "concussion" in terms and "stoppage" in terms
    assert all(t == t.lower() and not t.startswith("#") for t in terms)

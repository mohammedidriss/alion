"""Advice safety (coach.safety, ADR-018): the blocked-term check every AI answer
passes, and the safety rules every prompt carries."""

from __future__ import annotations

from coach import (
    CORNER_ADVICE_SYSTEM_PROMPT,
    FIGHTER_OBSERVATION_SYSTEM_PROMPT,
    REST_CARDS_SYSTEM_PROMPT,
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
        REST_CARDS_SYSTEM_PROMPT,
    ):
        assert prompt.endswith(SAFETY_RULES)
        assert find_blocked(prompt.replace(SAFETY_RULES, "")) == []
    assert "name" not in FIGHTER_OBSERVATION_SYSTEM_PROMPT.split("Your job")[0].split("fighter:")[1]


def test_the_blocked_terms_come_from_the_editable_file() -> None:
    terms = blocked_terms()
    assert "concussion" in terms and "stoppage" in terms
    assert all(t == t.lower() and not t.startswith("#") for t in terms)


# ---- ADR-039: broader medical language, without blocking coaching ----

COACHING = [
    "Keep your guard up and double the jab.",
    "Go to the body: the liver shot is open after the right hand.",
    "Medicine ball slams for hip rotation, three sets.",
    "Their right hand is dangerous; circle left.",
    "Dropping your hands is a fatal mistake.",
    "Head movement is the issue in round two; slip and pivot.",
    "Recovery between rounds was slower than round one.",
    "Avoid overtraining by keeping one easy day.",
    "Heart rate settled 27 bpm in 40 s.",
    "Signs of fatigue in the third: punch rate dropped 20%.",
    "Cut off the ring and work the kidney side with hooks.",
    "Fuel two hours before training; keep the weight trend at 0.5 kg a week.",
]

MEDICAL = {
    "Irregular heart rhythm in round 3.": "organ + problem",
    "Problems with the heart showed up on the strap.": "organ + problem",
    "Kidney damage from the body shots.": "organ + problem",
    "Showing symptoms after the clash of heads.": "symptoms",
    "Take ibuprofen after sparring.": "ibuprofen",
    "Use a sauna suit to drop the last kilo.": "sauna suit",
    "Consider a diuretic before the weigh-in.": "diuretic",
    "Looked dizzy in the corner.": "dizzy",
    "Heart rate dangerously high.": "dangerously high",
    "The fighter is overtrained.": "overtrained",
    "Medically, the HRV says rest.": "medically",
}


def test_coaching_language_passes() -> None:
    for text in COACHING:
        assert find_blocked(text) == [], text


def test_symptoms_medicines_water_cuts_and_organ_problems_are_caught() -> None:
    for text, why in MEDICAL.items():
        assert why in find_blocked(text), text


def test_the_rules_keep_body_data_to_training() -> None:
    assert "never as a sign of a health problem" in SAFETY_RULES
    assert "diuretics" in SAFETY_RULES and "medicines" in SAFETY_RULES

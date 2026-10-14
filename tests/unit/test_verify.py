"""The claim verifier (ADR-041): every gate a model's rest card must pass."""

from __future__ import annotations

from typing import Any

from coach.verify import check_card, verify_cards

FACTS: dict[str, dict[str, Any]] = {
    "F1": {
        "id": "F1",
        "kind": "change",
        "round": 2,
        "previous_round": 1,
        "value": 22,
        "previous": 41.5,
        "direction": "down",
        "quality": 0.9,
        "hand": None,
    },
    "F2": {
        "id": "F2",
        "kind": "hands",
        "round": 2,
        "value": 9,
        "of": 48,
        "hand": "lead",
        "quality": 0.9,
    },
    "F3": {
        "id": "F3",
        "kind": "rest",
        "round": 2,
        "value": 27,
        "of": 40,
        "direction": "down",
        "quality": 0.9,
    },
    "F4": {"id": "F4", "kind": "count", "round": 2, "value": 48, "quality": 0.3},
}


def card(slot: str, headline: str, cites: list[str], detail: str = "") -> dict[str, Any]:
    return {"slot": slot, "headline": headline, "detail": detail, "cites": cites}


def test_a_card_true_to_its_facts_passes() -> None:
    assert check_card(card("warning", "Output down 22% on round 1", ["F1"]), FACTS) is None
    assert check_card(card("warning", "Lead hand quiet", ["F2"], "9 of 48 punches"), FACTS) is None
    assert check_card(card("recovery", "Heart rate down 27 in 40 s", ["F3"]), FACTS) is None


def test_each_gate() -> None:
    gate = lambda c: (check_card(c, FACTS) or "").split(":")[0]  # noqa: E731
    assert gate(card("tactics", "Output down", ["F1"])) == "shape"
    assert gate(card("warning", "a b c d e f g h i", ["F1"])) == "shape"
    assert gate(card("warning", "Output down", [])) == "citations"
    assert gate(card("warning", "Output down", ["F9"])) == "citations"
    assert (
        gate(card("warning", "Heart rate down 27", ["F3"])) == "citations"
    )  # heart in a tactical slot
    assert gate(card("recovery", "Output down 22%", ["F1"])) == "citations"
    assert gate(card("warning", "Output down 25% on round 1", ["F1"])) == "numbers"
    assert gate(card("warning", "Output down by half", ["F1"])) == "numbers"
    assert gate(card("warning", "Lead hand quiet in round 9", ["F2"])) == "rounds"  # 9 is a count
    assert gate(card("warning", "Rear hand quiet", ["F2"])) == "hands"
    assert gate(card("warning", "Output up 22%", ["F1"])) == "direction"
    assert gate(card("warning", "Lead hand landed 9", ["F2"])) == "evidence"
    assert (
        gate(card("warning", "Output down 22%", ["F1"], "suggests growing tiredness"))
        == "inference"
    )
    assert gate(card("opportunity", "48 punches thrown", ["F4"])) == "quality"
    assert gate(card("warning", "Output down 22%, looks dizzy", ["F1"])) == "safety"


def test_one_card_per_slot_and_a_verdict_each() -> None:
    passed, verdicts = verify_cards(
        {
            "cards": [
                card("warning", "Output down 22%", ["F1"]),
                card("warning", "Lead hand quiet", ["F2"]),
            ]
        },
        list(FACTS.values()),
    )
    assert list(passed) == ["warning"] and passed["warning"]["cites"] == ["F1"]
    assert [v["ok"] for v in verdicts] == [True, False] and verdicts[1]["gate"].startswith("shape")
    assert verify_cards("not json", [])[0] == {}

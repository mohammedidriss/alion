"""Local and remote LLM setups (common.llm_setups, ADR-021): what counts as your
own network, choosing one at runtime, and the client following the choice."""

from __future__ import annotations

from pathlib import Path

import pytest

from common import get_settings, llm_setups


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:1234/v1",
        "http://192.168.68.117:11434/v1",
        "http://10.0.0.5:11434/v1",
        "http://172.20.1.2:11434/v1",
        "http://gym-laptop.local:11434/v1",
        "http://winbox:11434/v1",
    ],
)
def test_own_network_addresses(url: str) -> None:
    assert llm_setups.is_own_network(url)


@pytest.mark.parametrize(
    "url", ["https://api.openai.com/v1", "http://8.8.8.8:11434/v1", "https://example.org/v1"]
)
def test_public_addresses_are_not_your_own_network(url: str) -> None:
    assert not llm_setups.is_own_network(url)


def test_the_default_is_used_until_one_is_chosen_and_the_choice_survives(
    two_setups: Path,
) -> None:
    assert llm_setups.active_name() == "local"
    llm_setups.choose("remote")
    assert two_setups.exists() and llm_setups.active_name() == "remote"
    assert llm_setups.active() is not None and llm_setups.active().label == "Windows laptop"  # type: ignore[union-attr]
    with pytest.raises(ValueError):
        llm_setups.choose("cloud")


def test_the_client_follows_the_choice_and_test_overrides_still_win(
    two_setups: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from coach.llm_client import llm_config

    assert llm_config()[0] == "http://localhost:11434/v1"
    llm_setups.choose("remote")
    assert llm_config()[:3:2] == ("http://192.168.68.117:11434/v1", "gemma3:4b")
    monkeypatch.setenv("COACH_BASE_URL", "http://localhost:9999/v1")
    assert llm_config()[0] == "http://localhost:9999/v1"


def test_a_public_setup_is_refused_unless_allowed(
    two_setups: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ALION_LLM_REMOTE_URL", "https://api.openai.com/v1")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="own network"):
        llm_setups.choose("remote")
    monkeypatch.setenv("ALION_LLM_ALLOW_PUBLIC", "true")
    get_settings.cache_clear()
    assert llm_setups.choose("remote").url.startswith("https://api.openai.com")


def test_without_setups_the_single_url_is_used_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ALION_LLM_LOCAL_URL", "ALION_LLM_REMOTE_URL", "COACH_BASE_URL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("ALION_LLM_URL", "http://localhost:11435/v1")
    get_settings.cache_clear()
    try:
        from coach.llm_client import llm_config

        assert llm_setups.active() is None and llm_config()[0] == "http://localhost:11435/v1"
    finally:
        get_settings.cache_clear()

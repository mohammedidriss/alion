"""The LLM setups coach advice can use, and which one is in use (ADR-021).

Two named setups come from the settings (`.env`): "local" — usually Ollama on
this machine — and "remote" — another machine on your network (the Windows
laptop). The researcher picks one in the dashboard; the choice lives in
`data/llm_choice.json` and is read on every advice request, so switching needs no
restart.

Both must be on your own network — localhost, a private address (192.168.x.x,
10.x, 172.16–31.x), link-local, or a `.local`/`.lan` name — so session data never
goes to an internet API, unless `ALION_LLM_ALLOW_PUBLIC` says otherwise.
"""

from __future__ import annotations

import ipaddress
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from common.settings import get_settings

CHOICE_FILE = Path("data/llm_choice.json")
NAMES = ("local", "remote")
FALLBACK_MODEL = "gemma3:4b"


@dataclass(frozen=True)
class LlmSetup:
    name: str  # local | remote
    label: str  # what the researcher sees, e.g. "This computer"
    url: str
    model: str
    api_key: str

    @property
    def on_own_network(self) -> bool:
        return is_own_network(self.url)

    @property
    def allowed(self) -> bool:
        return self.on_own_network or get_settings().llm_allow_public


def is_own_network(url: str) -> bool:
    """True for localhost, private, link-local and loopback addresses, single-label
    hostnames and .local/.lan names — not for anything on the public internet."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host == "localhost" or "." not in host or host.endswith((".local", ".lan", ".home.arpa")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False  # a public DNS name
    return ip.is_private or ip.is_loopback or ip.is_link_local


def setups() -> dict[str, LlmSetup]:
    """The configured setups (a setup exists once its URL is set)."""
    s = get_settings()
    key = s.llm_api_key or "ollama"
    out: dict[str, LlmSetup] = {}
    if s.llm_local_url:
        out["local"] = LlmSetup(
            "local", s.llm_local_label, s.llm_local_url, s.llm_local_model or FALLBACK_MODEL, key
        )
    if s.llm_remote_url:
        out["remote"] = LlmSetup(
            "remote",
            s.llm_remote_label,
            s.llm_remote_url,
            s.llm_remote_model or FALLBACK_MODEL,
            key,
        )
    return out


def _choice_file() -> Path:
    return Path(os.getenv("ALION_LLM_CHOICE_FILE") or CHOICE_FILE)


def active_name() -> str | None:
    """The setup in use: the researcher's choice, else the default, else whichever
    is configured — None when no setup is configured."""
    configured = setups()
    if not configured:
        return None
    try:
        chosen = json.loads(_choice_file().read_text()).get("choice")
    except (OSError, ValueError, AttributeError):
        chosen = None
    for name in (chosen, get_settings().llm_default, *NAMES):
        if name in configured:
            return str(name)
    return None


def active() -> LlmSetup | None:
    name = active_name()
    return setups().get(name) if name else None


def choose(name: str) -> LlmSetup:
    """Use this setup from the next advice request on. Raises ValueError if it isn't
    configured or isn't on your own network."""
    setup = setups().get(name)
    if setup is None:
        raise ValueError(f"no '{name}' LLM is configured")
    if not setup.allowed:
        raise ValueError(f"{setup.url} isn't on your own network — advice data stays local")
    path = _choice_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"choice": name}) + "\n")
    tmp.replace(path)
    return setup

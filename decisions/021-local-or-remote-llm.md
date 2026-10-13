# 021. Local or remote AI — switched from the dashboard, kept on your own network

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

The coach's advice runs on Ollama, either on this Mac or on a second machine on
the network (a Windows laptop) to spare the Mac. Switching meant editing `.env`
and restarting the API, and when the laptop's address changed or its Ollama
stopped, advice failed until someone noticed. The requirements also say advice
data must not go to an external model API (R3.2).

## Decision

- **Two named setups in `.env`**: `ALION_LLM_LOCAL_URL`/`_MODEL`/`_LABEL` and
  `ALION_LLM_REMOTE_URL`/`_MODEL`/`_LABEL` (`common.llm_setups`). A setup exists
  once its URL is set; `ALION_LLM_DEFAULT` names the one used until someone picks.
- **Switched at runtime.** The choice is kept in `data/llm_choice.json` and read
  on every advice request — no restart. `coach.llm_client.llm_config` follows it
  (after the `COACH_*` test overrides, before the single `ALION_LLM_URL`, which
  still works when no setups are configured).
- **The AI model page** (`/ai-model`, researchers and admins; `GET/PUT /v2/llm`,
  `POST /v2/llm/test`) shows both setups — address, model, whether its server
  answers and has the model — with **Test** (one tiny request, timed) and **Use
  this one**.
- **Own network only.** Every request, and every choice, is refused for an
  address outside your own network (localhost, private, link-local, single-label
  or `.local`/`.lan` names) unless `ALION_LLM_ALLOW_PUBLIC` is set.
- Every advisory already records which model produced it (ADR-018), so a switch
  never silently mixes results.

## Alternatives considered

- **Fail over automatically to the other setup.** Advice would silently come from
  a different model mid-study; a visible, deliberate switch is safer.
- **Keep editing `.env`.** Needs a restart, which interrupts a recording.

## Consequences

- `tests/unit/test_llm_setups.py`, `tests/integration/test_llm_switch.py`.
- Reserve the remote machine's address in the router, or its setup breaks when
  DHCP hands it a new one.

# 049. Choosing among installed models, and comparing them

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

ADR-021 lets the researcher switch the coach's AI between two setups, this
computer and another on the network, each with one model named in `.env`. The
remote laptop has several models installed (gemma3, qwen), and the owner asked
(14 Oct 2026) to pick one from a list and compare how they do.

## Decision

- **A model per setup.** `GET /v2/llm` lists the models each setup's server
  offers (`/models`). `PUT /v2/llm {"choice", "model"}` uses that one from the
  next request on, no restart; it is refused when the server doesn't offer it.
  The pick is kept per setup in `data/llm_choice.json`, so switching setups back
  and forth keeps it; `.env` names the one used until a pick is made. Every piece
  of advice still records the model that wrote it (ADR-018).
- **Compare on the rest cards.** `POST /v2/llm/trial {"choice", "model",
  "session_id", "after_round"}` has that model phrase one round's rest cards
  exactly as in the rest minute — the same facts ledger, prompt and verifier
  (`rest_cards.phrase`, shared with the live route) — and returns how long it
  took, the cards written and passed, each failed gate, a blocked term if any,
  and the cards as they would show. The time limit is 90 s rather than the rest
  minute's 12, so a slow model is still measured; "in time" says whether it
  would have made the rest minute.
- The AI model page's **Compare** runs each chosen model (up to 4) over every
  round of a recorded session, one request at a time, after waking each model
  untimed (the first request after a pause also loads it), and shows the
  average and slowest time, rounds in time, cards passed of those written, the
  gate failed most, and each round's cards side by side.
- **Nothing reaches a coach or the advice record**: a trial is a measurement.
  It reads the session only if the caller may (the researcher; an administrator
  who isn't one may not), and refuses the coach-only study condition, as the
  rest cards do.

## Consequences

- Tests: `test_llm_switch.py` (picking an installed model), `test_rest_cards.py`
  (a trial: timed, verified, not recorded, access).
- Since ADR-058 comparisons are saved, run on the server, span several sessions
  and repeats, and are rated blind.
- One session's rounds are a small sample, and the model's output varies run
  to run: compare on several sessions before choosing.

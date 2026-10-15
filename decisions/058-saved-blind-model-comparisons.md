# 058. Model comparisons are saved, larger, rated blind, and actionable

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6

## Context

ADR-049's comparison ran in the browser on one session, once per round, and was
lost when the page was left; it measured speed and the verifier's verdicts, not
whether the cards were any good. The owner chose (15 Oct 2026) four additions:
save comparisons, compare on more data, rate the cards blind, and switch to the
winner from the results.

## Decision

- **Saved, run on the server** (`llm_comparison`, `llm_trial_result`; migration
  `f5c7e9b1d3a6`; `/v2/llm/comparisons`): a comparison is planned — up to four
  models, up to five recorded sessions, one to three runs of every round — and
  run in a background thread, one request at a time: each model woken untimed,
  then every round of every session, repeat by repeat, through `run_trial` (the
  rest minute's facts, prompt and verifier, ADR-049). It keeps going if the page
  is left, can be stopped, and stays in the history; one runs at a time, and one
  left running by a server restart is marked stopped with its trials kept.
- **Summary per model**: median and slowest time, rounds within the rest minute's
  12 s, cards passed of those written (and of the slots), **consistency** — of
  rounds run more than once, the share that passed as many cards every time —
  the gate failed most, failures, and the ratings.
- **Blind rating** (`llm_rating`): each model gets a code, A, B, … handed out in a
  shuffled order. Until "Reveal names" the results, the cards and the CSV show
  the code only; the researcher rates each model's cards for every round's first
  run, 1–5 — how useful to a coach in the rest minute — the models side by side in
  a shuffled order per round. A rating records whether it was given blind.
- **CSV** (`/v2/llm/comparisons/{id}/csv`): every trial as a row — timing,
  verdicts, failed gates, blocked terms, mean rating and how many were blind; the
  model's name once revealed.
- **"Use this one"**: once revealed, a model in the results is made the one in
  use, as on its setup card (`PUT /v2/llm`).
- Researchers only: a comparison reads the sessions' facts.

## Consequences

- `test_rest_cards.py`: a comparison runs every round and repeat, is rated blind
  then revealed, and exports.
- `routes/llm.py`'s single trial (`POST /v2/llm/trial`) stays, sharing
  `run_trial`.

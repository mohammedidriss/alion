# 019. Freezing advice — the study's stimuli don't change under the raters

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6 (RQ1 / expert review)

## Context

Raters and, later, experts score the platform's advice. For that to mean
anything, every rater must see the same advisory, and we must be able to say
exactly what produced it (requirement R5.9; an external review flagged it). Before
this decision, `force_regenerate` deleted the cached advice and replaced it, the
cache recorded only the prompt version, and nothing could stop an advisory from
changing mid-study.

## Decision

Built on `advice_record` (ADR-018), which already keeps every advisory with its
model, prompt version and SHA-256, input and output SHA-256, platform version and
time — rows are only added, so regenerating never erases a version.

- **Lock.** `POST /sessions/{id}/advice/lock?payload_mode=…` (researchers only)
  freezes the current shown advisory for that session and payload — for good.
  From then on the advice route returns exactly it (`locked: true`) to everyone,
  ahead of the cache and without calling the model; `force_regenerate` is refused
  (409). Withheld or failed advice can't be locked.
- **History.** `GET /sessions/{id}/advice/history` (researchers only) lists every
  advisory generated for the session — shown, withheld, failed — oldest first,
  with what produced each.
- **Traceable answers.** Every advice response carries `advice_id` (the record it
  came from, cached answers included) and `locked`.
- **Dashboard.** The RQ1 rater card offers researchers **Freeze for the study**
  once all four variants are shown; frozen advice is marked as such.

## Alternatives considered

- **Unlock.** A frozen stimulus that can be unfrozen isn't frozen; fixes go into
  a new prompt version after the review, as the study plan says.
- **Store the full input payload.** The SHA-256 proves which input produced an
  advisory without keeping another copy of training data; the input itself can be
  rebuilt from the session.

## Consequences

- `tests/integration/test_advice_freeze.py`.
- Still to build (the expert review study, R6): expert codes, follow/adjust/reject
  decisions with timing, trace view, trust questionnaire, immutable ratings.

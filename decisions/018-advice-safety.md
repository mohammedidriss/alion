# 018. Advice safety — training advice only, checked before it's shown

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

The study's advice must be non-binding training advice to a person — never a
diagnosis, a fitness verdict, a stoppage call or a medical clearance
(requirements R5.1, R5.2, R5.8). An audit found the opposite risk built in: the
prompts had no such rule, the weight prompt asked the model to judge
"unhealthy" weight loss and "dehydration risk", the fighter's name was sent to
the model, nothing checked an answer before it was shown, and the interface said
nothing about the advice's limits.

## Decision

- **Rules in every prompt.** `coach.safety.SAFETY_RULES` ends the corner-advice,
  observations and weight-analysis prompts: word advice as suggestions to a
  person who decides; never diagnose or name an injury or condition; never say
  anyone is fit, safe or unsafe, never recommend stopping or continuing, never
  imply clearance; for anything that may be a health matter say only "Worth
  checking with the team's medical staff". The weight prompt is rewritten around
  stability, trend, pace and practical fuelling. `PROMPT_VERSION` → v3.
- **A check on every answer.** `api/services/advice_gate.record` runs each
  answer through `coach.find_blocked` — whole-word, case-insensitive matches
  against `packages/coach/blocked_terms.txt` (diagnoses and conditions, fitness
  verdicts, stoppage and clearance), a plain file the researcher can edit. A hit
  withholds the advice: the user sees `coach.WITHHELD`, nothing is cached.
- **Every advisory recorded.** Table `advice_record` (migration `d2e8b4c6f9a1`):
  kind (corner, observations, weight), session/fighter, status (shown, withheld,
  failed), the terms that tripped it, the output (withheld ones too, for review),
  the model, prompt version and SHA-256, input and output SHA-256, platform
  version, who asked. Rows are only added. ADR-019 builds the advice freeze on it.
- **No names to the model.** The weight and observations payloads drop the
  fighter's name (age stays — it matters for recovery).
- **Notices.** Every advice card shows "AI training advice from an early version
  — it can be wrong. Never a diagnosis, a medical clearance, or a call to stop or
  continue. A person makes every decision." (or that the safety check withheld
  it). Every signed-in page carries a permanent line: "Alion is an early version
  still in development and can make mistakes — a person makes every decision."

## Alternatives considered

- **Prompt rules only.** A small local model doesn't always follow them; the
  check catches what slips through.
- **Rewrite blocked sentences instead of withholding.** An edited advisory is no
  longer the model's output, which the study measures; withholding keeps the
  record honest.
- **A classifier instead of a term list.** Opaque and another model to validate;
  a readable list the researcher controls fits the study better.

## Consequences

- Some legitimate advice will be withheld (e.g. "warm up to avoid injury"). That
  is the safe failure; `advice_record` keeps them for review, and the list can be
  tuned.
- `tests/unit/test_advice_safety.py`, `tests/integration/test_advice_gate.py`.

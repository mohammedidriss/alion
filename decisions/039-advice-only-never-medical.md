# 039. Advice only, never medical — every path, every time it's shown

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

ADR-018 put safety rules in every prompt and a blocked-term check on every AI
answer. An audit of every place the platform writes advice or verdict-like text
found it holds for the three AI features (corner advice, weight ideas, fighter
observations), and that nothing computed outside the AI gives a medical verdict:
readiness is "above / near / below baseline" against the fighter's own history,
and Health notes only show what people type. Five gaps remained:

1. Cached corner advice was served without being checked again, so a term added
   to the list didn't stop advice cached before it.
2. Frozen study advice was served from its record as written.
3. An answer that looked like a failed call ("Failed to connect…") skipped the
   check.
4. Appropriate-reliance study snapshots — written by researchers — had no check
   at all, at creation or when shown to reviewers.
5. The list missed symptoms, medicines, weight cutting by dehydration, and
   phrases pairing an organ with a problem ("irregular heart rhythm").

## Decision

- **Checked again whenever stored advice is shown**: the corner cache, frozen
  advisories and study snapshots. Anything that now trips the check is replaced
  by the withheld notice (`advice_gate.still_safe`).
- **Every answer is checked**, including ones that look like failures; a blocked
  term makes it `withheld` whatever else it says.
- **Study snapshots with medical wording are refused** (422, naming the terms),
  and a snapshot that trips a later-added term reaches reviewers as the withheld
  notice with no claims.
- **More blocked language** (`coach/blocked_terms.txt`): symptoms (dizzy,
  headache, nausea…), conditions (asthma, hypertension, tachycardia…), injuries
  (sprain, ligament, torn…), medicines (ibuprofen, painkillers, steroids…), weight
  cutting by dehydration or not eating (diuretics, laxatives, sauna suits, water
  cutting, starving), and more verdicts (unfit, not safe, dangerously high, health
  problem…). Plus one pattern: an organ (heart, brain, lungs, kidneys, blood
  pressure) within a few words of a problem (problem, damage, abnormal,
  irregular, disease…). Checked against coaching language so ordinary advice
  still passes: "medicine ball", "liver shot", "a dangerous right hand", "a fatal
  mistake", "head movement is the issue", "avoid overtraining".
- **Stricter prompt rules**: heart rate, HRV, weight and punch data are read only
  as training load, effort, pacing, recovery or technique — never as a sign of a
  health problem or a comment on any organ; no medicines or supplements as
  treatment; no weight loss by dehydration or not eating. `PROMPT_VERSION` v4, so
  cached v3 advice is regenerated under the new rules.

## Consequences

- `tests/unit/test_advice_safety.py` (coaching passes, medical is caught) and
  `tests/integration/test_advice_only.py` (cache, frozen, failure-looking reply,
  study refusal, reviewer re-check).
- A word list and one pattern can't catch every paraphrase; the prompt rules,
  the always-visible "training support only — not medical advice" boundary
  (ADR-024) and the person who decides remain the other layers.
- A reviewer shown a withheld advisory mid-study still answers it; the export
  keeps the snapshot, so researchers can exclude it.

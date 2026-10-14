# 026. The appropriate-reliance study — ported from the Proposal V2 test build

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 7 — dissertation validation study

## Context

The revised dissertation asks whether combat-sports experts rely appropriately on
non-binding, evidence-traceable AI advice: follow it when it's right, catch it
when it's wrong (H1), how trust and distrust move after an error and a recovery
(H2), and whether opening the evidence relates to the decision (H3). The RQ1
rater card only scores advice quality, and ADR-019 left the review study to
build. A separate Codex test build (another repository, on an older version of
this app) added the data model, an API and a one-page flow. Its model and intent
were sound; it predated ADR-017 to ADR-025 and its flow had gaps: the reviewer
picked each advisory and labelled each check-in "post-error" or "post-recovery"
themselves (they can't know — correctness is blinded), the opening survey ran
again per advisory, codes and consent were typed and ticked by the reviewer, the
API let admins coordinate and any coach or referee see any session's advice, and
there was no export.

## Decision

- **Data** (from the test build): an immutable `study_advice_snapshot` per
  adjudicated advisory — exact input, output, model, prompt version and their
  hashes, and the correctness verdict with its note — split into
  `study_advice_claim`s, each with its bounded evidence (stream, time window,
  quality). Reviewers' evidence opens, follow/adjust/reject decisions (with
  response time and position in their sequence) and trust/distrust check-ins are
  recorded once and can't be changed. Migration `e5a7c9d1b3f2`.
- **Reviewers are enrolled by a researcher** (ALION_RESEARCHERS) once the signed
  consent form is checked: a coach or referee account gets a code (`RV-001`, …)
  tied to its login. Every study record carries the code, never the name; only
  researchers see the mapping.
- **The server runs the sequence** (`services/reliance.py`): the opening check-in,
  then every advisory in an order counterbalanced per reviewer (a stable hash of
  code and advisory), a check-in right after the first incorrect advisory, and
  one after two correct advisories have followed it (or at the end). Reviewers
  see "Check-in 2" and "Advisory 3 of 8"; the time point, the correctness and the
  session stay on the server. A decision or check-in out of turn is refused.
- **Trust questionnaire**: Jian, Bisantz and Drury's checklist structure — 5
  distrust and 7 trust items on a 1–7 scale, scored separately. The wording lives
  in `services/reliance_trust_items.json`, to be pasted from the approved
  protocol; until it is, the study stays closed to reviewers.
- **Researchers** see the questionnaire's status, enrol reviewers, freeze
  advisories (JSON, as the API takes them) and export everything by code, each
  decision classed as appropriate reliance, appropriate self-reliance,
  over-reliance, under-reliance or an adjusted correct advisory.
- `/study` in the dashboard, linked for researchers, coaches and referees.
- Not taken from the test build: its safety check (ADR-018's is stronger), its
  test-build theme and banner, and its own versions of fixes already made here.

## Consequences

- `tests/integration/test_api_reliance.py`.
- Still the protocol's job: approval, independent adjudicators, the questionnaire
  wording, the number and mix of advisories. A check-in that follows an incorrect
  advisory can hint that it was incorrect — the protocol decides whether to add
  neutral check-ins elsewhere.
- Advisories are authored as JSON for now; building them from frozen advice
  (ADR-019) in the page is a later step.

## Update — 2026-10-14

The questionnaire now carries the published checklist: Jian, Bisantz & Drury's
12 items (5 distrust, 7 trust, 1 = "Not at all" … 7 = "Extremely"), worded as
reproduced in Table 1 of *Measuring trust in artificial intelligence: validation
of an established scale and its short form*, Frontiers in Artificial
Intelligence (2025), doi:10.3389/frai.2025.1582880, CC BY. The check-in tells
reviewers that "the system" means the AI advisories. The study is open to
enrolled reviewers once advisories are added.

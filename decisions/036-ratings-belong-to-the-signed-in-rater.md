# 036. RQ1 ratings belong to the signed-in rater, and earlier scores are kept

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The external (Codex) review found the RQ1 rater card's scores unreliable as study
data: the rater typed their own id, so two raters could type the same one and
overwrite each other, and changing a score overwrote it with no trace. Anyone
signed in could also read every rater's scores.

## Decision

- **The rater is whoever is signed in.** Each score stores the account
  (`rq1_rating.user_id`) and a rater code made from it, `R-` + the first 8 hex
  characters of the account id — the code is what exports and the aggregation
  read, never a name or email. A typed `rater_id` is ignored. The card shows
  "Rating as R-…".
- **A changed score is a new row**; the old one gets `superseded_at` and is kept.
  Sending the same score again changes nothing.
- **Raters see only their own scores** (`GET /studies/rq1/sessions/{id}/ratings`),
  so ratings stay independent; **the bulk read is for researchers**
  (`GET /studies/rq1/ratings`, current scores, `?history=true` for every version).
- Migration `a1c3e5f7b9d2` adds the two columns; earlier rows keep their typed id
  and no account.

## Consequences

- `tests/integration/test_rq1_ratings.py`.
- The appropriate-reliance study (ADR-026) already ties every answer to an
  enrolled reviewer; this brings RQ1 in line.

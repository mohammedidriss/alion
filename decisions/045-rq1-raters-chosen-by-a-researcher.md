# 045. RQ1 is rated only by researchers and the coaches they choose

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The "RQ1 — Coach rater (blinded)" card — four advice variants from different
sensor subsets, scored 1–5 on four criteria (ADR-036) — showed on every session
page to anyone who could open the session, fighters included, and anyone could
score. RQ1's raters are certified coaches the researcher recruits.

## Decision

- **A list of raters** (`rq1_rater`, migration `c5e7a9b1d3f6`): researchers add a
  coach account by email and remove it (`GET/POST /studies/rq1/raters`, `DELETE
  /studies/rq1/raters/{user_id}`) from the Study page. Only coach accounts can be
  raters; the RQ1 raters list is separate from the appropriate-reliance study's
  reviewers (ADR-026).
- **Only researchers and raters rate**: `/studies/rq1/me` says `can_rate`; scoring
  and reading one's own scores are refused (403) for anyone else; the card shows
  only when `can_rate`.
- Removing a rater stops further scoring; the scores they gave are kept.

## Consequences

- `tests/integration/test_rq1_ratings.py`.
- Unchanged: a rater only opens the sessions they already could (their own
  fighters'). Letting raters open other fighters' sessions for the study would be
  a separate access decision.

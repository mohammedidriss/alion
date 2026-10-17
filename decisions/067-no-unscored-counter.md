# 067. A camera counter scored on nothing is never used

- **Status**: Accepted
- **Date**: 2026-10-16
- **Phase**: 6
- **Amends**: ADR-059 (training), ADR-064 (which counter is used)

## Context

On 15 Oct 2026 a camera counter was trained from the Single round dataset, three
minutes after RQ2's v2. Single round has only single-punch takes, and with one
participant those all train (the pilot split), so nothing was left to test on.
Its report reads F1 0.0 against the detector's 0.0 on 0 test punches. Being the
newest, it counted every camera from then on: first by file date (ADR-059), then
under ADR-064's rule, which only refused a counter *worse* than the detector,
and 0.0 isn't worse than 0.0.

## Decision

- **A counter with no test punches is never used.** It can't be shown to beat
  the detector. The choice stays: the newest by training date among counters
  that, on their own test, beat it.
- **Training refuses a dataset with nothing to test on** (409, before it starts,
  and in the run itself). The message says to train from a dataset with combo
  or free blocks (RQ2), with "also learn from the other datasets" on, so this
  one's takes join the training.
- The unscored Single round counter stays on disk, unused.

## Consequences

- `test_training.py`: a dataset whose export has no test stretches is refused,
  with the reason.
- `test_counting.py`: a newer counter scored on nothing loses to an older, scored
  one.

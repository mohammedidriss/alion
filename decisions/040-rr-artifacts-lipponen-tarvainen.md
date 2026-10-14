# 040. Heart-rate artifacts found the Lipponen–Tarvainen way

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

ADR-037 removed artifacts with a fixed rule: more than 20 % from the median of
the beats around it. The RingsideIQ review board (14 Oct 2026) pointed to the
Lipponen–Tarvainen method behind Kubios' automatic correction as the stronger
reference, and to evidence that RMSSD is biased once more than about 1 % of
beats are artifacts. A fixed 20 % misses smaller ectopic beats when variability
is low, as it is during exercise.

## Decision

`analyze.rr_artifacts.classify` implements the method's detection
(Lipponen & Tarvainen 2019, J Med Eng Technol 43:173–181):

- two adaptive thresholds, 5.2 × the quartile deviation over 91 beats — one on
  successive differences, one on each interval's distance from the median of
  its 11 neighbours (shortening counted double);
- each outlier classed as ectopic, missed (one interval about twice the median),
  extra (two short intervals adding up to about the median — both removed) or
  long/short.

`clean_hrv` removes an interval when it is out of range (300–2000 ms), classed
by the method, or more than 20 % from its local median. The last rule stays as a
backstop: the adaptive thresholds need a few dozen beats to learn the fighter's
variability, and short recordings don't have them. Artifacts are deleted, not
interpolated, and RMSSD is never computed across a removed beat (ADR-037).

One departure from the paper: both thresholds are floored at 30 ms, so a near-
constant series (quartile deviation → 0) doesn't turn every ordinary beat into
an outlier. Real artifacts are hundreds of milliseconds off.

On the live database: the 6,800-beat session now loses 57 beats (0.8 %, RMSSD
13.8 → 12.2 ms) that the fixed rule kept; one 64-beat session loses 3 (RMSSD
31.2 → 20.5 ms). The 5 % reliability line is unchanged.

## Consequences

- `tests/unit/test_hrv_metrics.py`: natural variability is left alone (≤ 0.5 %),
  and a missed, an extra and an ectopic beat are each classed.
- The H10's raw ECG, which could confirm a beat, isn't recorded; that check
  stays open.

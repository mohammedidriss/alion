# 020. Punch types — a learned classifier names each punch

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6 (datasets / RQ2)

## Context

The trained camera counter (ADR-013's training step) finds when a punch happens
and with which hand, but not what it is. The only namer was a rule
(`analyze.punch_type_heuristic.classify_punch_type`): the wrist's dominant
direction over the last five frames, untested against real labels. The dataset's
labels already carry the type — every single-punch category and combo is typed
(jab, cross, hook, uppercut); free shadowboxing isn't.

## Decision

A second classifier (`analyze.punch_model`), trained in the same run:

- **It learns the motion, not the name**: straight, hook or uppercut, from the
  same mirrored arm features the counter uses, over ±300 ms around the punch
  (gradient-boosted trees, classes balanced). Jab vs cross follows from the hand
  and the stance — a jab is the lead hand's straight (`punch_name`) — so one model
  serves orthodox and southpaw fighters and learns from both arms at once.
- **Trained** on the typed labels of the train stretches (every camera).
- **Scored** on the test stretches' typed punches two ways, both in the report
  under `types`: given the true punch (each label's moment), next to the current
  rule-based namer — accuracy, per-type share named right, and a confusion table;
  and end to end, on the counter's own punches that match a label.
- **Saved** with the counter in `v{n}.joblib` (`type_model`, `type_classes`).
- The dataset page's training card shows it next to the counter's result.

## Alternatives considered

- **One model for count and type together** (a "jab frame", "hook frame"… class
  per frame). Splits the scarce punch frames four ways and couples two problems
  that are easier apart; the counter is already good.
- **Four classes including jab vs cross.** The difference is which hand leads —
  known exactly from the stance; learning it would tie the model to one stance.

## Consequences

- With the pilot split (one fighter), the test punches are the combos, so
  uppercuts — no combo has one — are trained but not tested until a full or
  multi-fighter split exists.
- Labels are auto-labels from the wrist sensors; their types come from the
  category being recorded, not from review.
- `tests/unit/test_punch_model.py` (the synthetic boxer throws hooks and
  uppercuts now), `tests/integration/test_training.py`.

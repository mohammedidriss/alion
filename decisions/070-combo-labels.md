# 070. A combo's punch is the strongest burst near its turn

- **Status**: Accepted
- **Date**: 2026-10-17
- **Phase**: 6
- **Amends**: ADR-013 (the protocol's auto-labels)

## Context

A combo block is labelled from the wrists (`dataset_protocol._label_combos`):
1. the bursts of both wrists are grouped into combos;
2. each combo's sequence is walked in order, and every punch took the **first**
   burst on its own wrist.

Checking the jab-cross take 81c32f76 (17 Oct 2026) turned up two errors:
- **A twitch took the jab's label.** At 17.41 s and 38.25 s the lead wrist gave
  a small burst (about 1.2 g) and the arm didn't move on any camera. The jab came
  0.3 s later (2.6–4.1 g, full extension on all three cameras). The label sat on
  the twitch, 0.3 s early. For training, that makes the real jab a "no punch" for
  both counters.
- **A combo started before the cue was dropped.** The jab came 0.5 s before the
  block began. Only bursts inside the block were read, so the cross was left
  without its jab and the whole combo went unlabelled.

Across all 14 combo blocks (505 labels), measured against the wrist counter's
punches that at least two cameras confirmed:
- 11 labels sat 0.15–0.5 s early;
- 23 confirmed punches had no label on them.

Most were in RQ2, where combo blocks are the camera counter's test (pilot split).

## Decision

- **Each punch takes the strongest of its wrist's bursts within 400 ms of the
  first one it may take** (`_combo_picks`, `COMBO_LOCAL_MS`). The rest of the
  combo must still be able to follow, so a double jab keeps a soft first jab.
  Ties go to the earliest burst.
- **A combo started up to 1 s before the cue counts** (`COMBO_PRE_CUE_MS`). The
  bursts are read from a second before the block, and a group with no burst
  after the cue isn't the block's. Blocks are at least 5.3 s apart in every take
  so far, so the previous block can't leak in.
- **The provenance records it**: `labels.detector.combo` in protocol.json holds
  the detection settings, the window and the reach before the cue.
- **The labels stay the wrists' alone.** The cameras were used only to choose
  the rule, never inside it.

### Choosing the rule

On the 14 combo blocks, with the 1 s reach before the cue:

| Rule | On a confirmed punch | Early | Confirmed, unlabelled |
|---|---|---|---|
| First burst (before) | 92.7% | 11 | 23 |
| Strongest set for the whole combo | 94.7% | 2 | 13 |
| **Strongest within 400 ms (chosen)** | **94.5%** | **2** | **14** |

- The whole-combo version scores a little higher. But where two combos run
  together with no clear pause, it can skip the first one and label the second.
- The window's result is the same anywhere from 350 to 500 ms. At 250–300 ms it
  is too short to reach past a twitch.

### Existing labels

Regenerating whole takes wasn't safe. Today's code, even before this change,
doesn't reproduce some of the saved labels:
- **lead_hook (3f27630c) and rear_hook (64b51881):** it would add a hook at the
  block's very end (52.3 s and 52.6 s). This looks like the end-of-take movement.
- **combo_12 (1ac257bd):** it would drop a camera-confirmed combo that runs into
  the one before it.
- **combo_112 (93947cd3):** two labels differ.

So only this rule's own change was applied to the saved labels. That change is
what today's rule produces against what the new one does. The labels were backed
up first, and the take's `sha256` and provenance were updated, so the labels
stay generated, not reviewed.

| Take | Block | Labels moved |
|---|---|---|
| 2968bbfc | combo_123 | 2 (lead hooks) |
| 31d869b2 | combo_32 | 2 (lead hooks) |
| 8c87402d | combo_112 | 5 (jabs) |

- 7 of the 9 move from early onto a confirmed punch.
- One goes from late to a spot with no confirmed punch.
- One is a swap inside a triple jab.
- 93947cd3 already had the new rule's labels.
- The hand-reviewed jab-cross take 81c32f76 is exactly what the new rule
  produces: 30 labels, 15 complete combos.

## Consequences

- **The camera counter in use (v4) barely moves** when re-scored on RQ2's test
  with the corrected truth:
  - combos: F1 0.965 → 0.966;
  - all test stretches: 0.933 → 0.934.
  Scores before and after stay comparable, so it isn't retrained for this.
- The wrist counter trains on combo labels (ADR-060). Its next training no longer
  learns the 9 moved jabs and hooks as non-punches.
- The labels that today's code doesn't reproduce are left as they are; it's the
  owner's call whether to review them.
- `test_api_protocol.py`:
  - a twitch before the jab doesn't take its label, and the provenance names the rule;
  - a soft first jab of a double jab is kept;
  - a combo started just before the cue counts;
  - a combo finished before the cue isn't the block's.

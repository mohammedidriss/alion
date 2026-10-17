# 068. Free shadowboxing is labelled by the wrist counter

- **Status**: Accepted
- **Date**: 2026-10-17
- **Phase**: 6
- **Amends**: ADR-013 (the protocol's auto-labels), ADR-060

## Context

A take's labels are made per block (`dataset_protocol.label_block`):
- single-punch blocks use their punch type's own settings (`PROFILES`);
- combos use the combo rules;
- free shadowboxing, any type on either hand, used the detector's fixed
  settings.

ADR-060 showed those fixed settings miss gentle hooks and count an uppercut's
return to guard as a second punch. In RQ2 the free blocks are the camera
counter's main test (pilot split), and their labels are its truth. The owner
chose (17 Oct 2026) to label them with the wrist counter.

## Decision

- **A free block is labelled by the wrists' trained counter** (`_label_free`).
  The counter sees a second past each edge for context, and the punches inside
  the block are kept, on either hand, with no type.
- **If no counter is trained**, the fixed settings label it, as before.
- The same goes for a free block's live count while it records (`read_imu6`
  gives the counter the rotation it needs).
- **The provenance records it**: `labels.detector.free` in protocol.json is the
  counter's version, or "detector" if there is none.
- **No circularity**: the wrist counter never trains on free blocks (ADR-060), so
  it isn't learning from its own labels.
- RQ2's four takes with a free block were regenerated (none hand-edited). Their
  labels were backed up first.

## Consequences

Measured on copies of the four takes before regenerating (wrist counter v1):
- **Only the free blocks change.** Every other block's labels are identical.
- **Free shadowboxing goes from 1,103 labels to 943.** 184 labels go and 24 come
  in. The takes:
  - 68910f99: 263 → 231
  - 8c7522ee: 267 → 219
  - 8c87402d: 292 → 253
  - 96d051d4: 281 → 240
- **The cameras' 3D pose agrees.** At the moments removed, the arm extends a
  median of 4 cm, and 1% extend more than 15 cm. At those kept, the median is
  11 cm, and 28% extend more than 15 cm. The removed labels were mostly returns
  to guard.
- The camera counter's test truth on free shadowboxing changes, so its scores
  before and after this aren't comparable. It's re-scored on the new labels.
- `test_api_protocol.py`:
  - with a counter, a free block is its punches inside the block, with the
    provenance naming it;
  - without one, the labels are as before, and the provenance says "detector".

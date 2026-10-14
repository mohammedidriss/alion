# 032. The live punch box shows counts, not types — for now

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The live box on every camera (ADR-022) named each punch with the browser's quick
rule (`classifyPunchType`, the wrist's direction over the last frames). Scored on
the 1,472 typed punches of the dataset takes, as each of their three cameras saw
them (4,414 views), its Python twin (`punch_type_heuristic`) named **27.8 %**
right — worse than guessing; straights 33 %, hooks 36 %, uppercuts 1 %
(branch `research/boxingvi-camera-types`, `docs/studies/BOXINGVI_CAMERA_TYPES.md`).
Showing those types live misleads.

## Decision

- **Off live** (`LIVE_TYPES = false` in `lib/punchTally.ts`): the box on each
  camera's video shows the total and each hand's count; the panel under the
  cameras and each bout corner show each hand's total, with "Punch types appear
  on the session page after you stop, named from the wrist sensors."
- The tally is still counted and sent with the heartbeat, so the types can come
  back on when a better model runs live.
- After the session, types come from the wrist type model (ADR-029) on the
  session page — unchanged.

## What a better live model could be

On the same takes, held out by take (one participant): the ADR-020 3D camera
model named 95.1 % from one camera and 97.5 % with the three cameras averaged;
one camera with the wrist model 96.6 %; three cameras with the wrist 96.7 %
(`research/camera-wrist-fusion`, `docs/studies/CAMERA_WRIST_FUSION.md`). A model
trained on BoxingVI's 2D pose of 18 other athletes reached 51.0 % on these
cameras and added nothing when mixed in — not used.

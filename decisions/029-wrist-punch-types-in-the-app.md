# 029. Punch types from the wrist sensors, shown in the app

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

ADR-028 measured a wrist-only punch-type model: 85.1 % on takes it never trained
on (straight / hook / uppercut; 51.3 % by always guessing straight), 152 / 152
on combinations — one participant, orthodox only. The researcher chose to show it
in the app, with that score next to it.

## Decision

- **Trained from the takes, by a researcher.** `services/wrist_type_model.py`
  reads every completed take's typed labels straight from the take folders (no
  export), scores the model on takes held out (5-fold, grouped by take) and on the
  combinations (trained on single-type blocks), fits on everything and saves a
  numbered version with its report in `data/ml/wrist_types/` (git-ignored, like
  the camera models: it is trained on participants' data).
  `POST /v2/wrist-types/train` and `GET /v2/wrist-types` are researcher-only; the
  Datasets page shows the newest version's score and a Train button. One run at a
  time.
- **It names every wrist punch.** The newest version runs inside the wrist ↔
  camera cross-check: each punch the wrists felt gets its motion, and its type —
  jab or cross from the hand and the fighter's stance, hooks and uppercuts as
  they are (no jab/cross without a fixed stance). The model version is part of
  the cross-check's signature, so training a new version names every session's
  punches again the next time it's opened.
- **Shown on the session's per-round breakdown**: the session's type mix as the
  coloured dots the cameras use (per hand; Jab / Cross / Lead and Rear hook and
  uppercut by the stance), labelled with the model version and how often it was
  right on recordings it never trained on, and a per-round "Types" line.
  Camera-only punches (a wrist sensor wasn't streaming) aren't named.
- Not taken here: types for sessions without camera pose (no cross-check), and
  types in the Observations trend — later steps.

## Consequences

- `tests/integration/test_wrist_type_model.py`,
  `tests/integration/test_cross_check.py` (naming through the cross-check and
  the round export).
- The score in the app is only as wide as the dataset: one participant today.
  Retrain as other fighters' takes come in; the card says so while there are
  fewer than three participants.

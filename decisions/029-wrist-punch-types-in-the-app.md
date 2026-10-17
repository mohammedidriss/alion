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

## Update — tested on other boxers (2026-10-14)

On the public Zenodo "Boxing punch data" set (Manoharan, doi:10.5281/zenodo.14965635,
CC BY 4.0 — elite boxers, IMU under the glove, 200 Hz, one file per punch type,
no boxer, stance or punch marks; kept in `data/external/`, git-ignored), resampled
to 100 Hz and read as orthodox (lead = left): version 1 named **49.6 %** of 893
punches right — hooks 90–97 %, lead uppercuts 60 %, lead jabs 48 %, rear jabs 5 %
and rear uppercuts 19 % (both mostly taken for hooks). Gravity at guard points
differently in their sensors; rotating their axes into ours (gravity + the
straight-punch direction) only reached **52.0 %**, and a direction-free model
33 %. So the 85 % holds for the participant it was trained on, not for other
boxers yet. `scripts/studies/zenodo_wrist_eval.py` re-runs the test.

## Update — sensors worn on swapped wrists (2026-10-17)

A take whose sensors were worn on the wrong wrists (`imu_hands_swapped` in its
protocol.json, the protocol card's Swap wrists) keeps imu.csv raw; its labels.json
is corrected. Training read the raw file, so every label in such a take got the
other wrist's signal — in the RQ2 dataset two takes (8c87402d, 96d051d4), 468 of
the 1,591 typed labels. Training now reads those takes the way they were worn
(`_imu_streams(folder, swapped=…)`, which the wrist counter of ADR-060 uses as
well). Versions 1 and 2 were trained after both takes were marked, so their
85.1 % includes those punches read from the wrong wrist. On the same takes
(1,590 typed punches, 17 Oct 2026), held out, the fix alone takes the model from
**85.3 % to 96.0 %**: straights 89 → 99.6 %, hooks 84 → 96 %, uppercuts 77 → 85 %.
The next version is the first on the corrected signal. The camera type model needs nothing: it pairs the
labels with the arms the cameras see, not with imu.csv. The other boxers' set
has no swapped takes. Test: `test_a_take_worn_on_swapped_wrists_is_read_the_way_it_was_worn`.

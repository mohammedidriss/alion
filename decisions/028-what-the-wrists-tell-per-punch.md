# 028. What the wrist sensors tell per punch: force, rotation, type — not speed

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The wrist sensors (WT901 ×2, 100 Hz) record acceleration (g) and rotation (°/s).
Each counted punch already carried its peak force. The question was what else
they can give per punch: how fast the forearm turned, the punch type, and the
hand's speed — each measured before it is shown.

## Decision

1. **Rotation per punch — shown.** `analyze.imu_punches.peak_rotations`: the
   fastest the forearm turned (|ω|, °/s) within ±150 ms of each wrist punch. It
   rides through the wrist ↔ camera cross-check (`peak_dps` on each punch;
   cross-check VERSION 3, so sessions recompute when opened) and the wrist-only
   counter, and is shown next to force: the per-round breakdown ("Rotation") and
   the Observations table; the AI observations get `avg_punch_rotation_dps`.
   On the 13 Oct session: all 193 counted punches, median 885 °/s (p10 280,
   p90 1,410).

2. **Punch type from the wrists — measured, not yet shown.**
   `analyze.wrist_types`: a 600 ms window of acceleration and rotation around
   each punch → shape statistics, peak timing, how far the forearm turned, and
   the window itself → gradient boosting over straight / hook / uppercut (jab or
   cross from the hand and the stance). `scripts/studies/wrist_type_eval.py` on
   the 1,471 typed punches of 24 dataset takes:
   - takes held out (5-fold, grouped by take): **85.1 %** (always guessing
     "straight": 51.3 %); recall straight 89.8 %, hook 83.2 %, uppercut 75.5 %
     (uppercuts mostly taken for hooks); left 83.7 %, right 86.7 %;
   - combinations, trained on single-type blocks only: **152 / 152** (straights
     and hooks — no uppercut in the combos);
   - random forest 86.9 %, per-hand models 82.9 %, logistic regression 77.8 %:
     gradient boosting kept.
   Caveats: one participant, orthodox only. Showing it in the app waits for the
   researcher's decision; when it is, the model is trained from the dataset like
   the camera models (ADR-020) and names each wrist punch in the cross-check.

3. **Speed from the wrists — not shown.** `analyze.wrist_speed`: gravity from the
   guard before the launch, the forearm's turn from the gyro, then the remaining
   acceleration integrated to the peak. `scripts/studies/wrist_speed_eval.py`
   against the cameras' speed on 2,368 punches both saw: Pearson **0.05**; the
   estimate spreads 0.8–7.4 m/s. The cameras' per-punch speed also doesn't track
   the wrists' own force (0.01) or rotation (0.00) — which do track each other
   (0.32) — so it is too noisy to be a reference. A wrist speed needs a
   calibrated reference (radar, or high-speed video with a known scale) before
   it can be trusted; and the cameras' speed, and the score built on it, are a
   rough relative index, not a measurement.

## Consequences

- `tests/unit/test_imu_punches.py`, `tests/unit/test_wrist_motion.py`,
  `tests/integration/test_cross_check.py`, `tests/integration/test_api_session_metrics.py`.
- The two evaluation scripts are kept to re-run as the dataset grows (more
  participants, a southpaw, uppercuts in combos).

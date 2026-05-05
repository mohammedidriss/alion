# 003. CV must report punch velocity (scope amendment)

- **Status**: Accepted
- **Date**: 2026-05-05
- **Phase**: 1 (amendment)

## Context

The original brief assumed three orthogonal sensor streams — CV (what happened), IMU/Hykso (how fast), HRV (physiological state) — and the fusion engine would cross-check them. Velocity in `analyze/punch_detector_heuristic.py` is documented as a "stand-in until the IMU stream lands."

After research, Hykso and equivalent boxing IMU wrist trackers are not currently available for purchase. The user is searching for alternative trackers in parallel, but cannot block engineering progress on hardware that may or may not arrive.

## Decision

**CV is amended to be a real velocity source, not a placeholder.**

When IMU eventually lands (alternate tracker, future Hykso restock, or other), it remains the ground-truth source per the original brief. CV-derived velocity stays in the system as either (a) the sole source if no IMU, or (b) a sanity-check against IMU when both are present.

Engineering targets, in priority order:

1. **Tier A** — switch the pose pipeline from 2D image-plane landmarks to MediaPipe `pose_world_landmarks` (3D, hip-centered, calibrated to meters by the ML model). Single biggest accuracy gain available.
2. **Tier C** — cubic-spline sub-frame interpolation to recover peak velocity that 30 fps undersamples on fast punches.
3. **Tier B / E** — per-frame shoulder-width self-calibration as a sanity check, with an optional per-fighter `shoulder_width_m` override on the `Fighter` record.
4. **Tier D** — 3D velocity vector with toward-camera vs lateral direction labels, so straight punches stop being undercounted.

Combined realistic accuracy target on a single laptop webcam at desk distance: **±15% lateral, ±25% straight punches** — defensible for a single-camera setup, with the limitation disclosed in the dissertation methodology.

## Alternatives considered

- **Wait for IMU hardware before continuing.** Rejected: timeline unknown, blocks all other Phase 1 work.
- **Multi-camera triangulation now.** Rejected: high effort, requires gym-grade setup, deferred to Phase 6+ if needed.
- **Drop velocity entirely from the system.** Rejected: a coaching system without "how hard / fast" loses meaningful information.

## Consequences

- Positive: the project is no longer hardware-blocked on velocity. Single-laptop demo path works end-to-end.
- Negative: validation study may need to drop a condition (5 → 4) — CV-only / HRV-only / CV+HRV / control. To be discussed with the dissertation advisor; not blocking.
- Follow-up: `analyze/punch_detector_heuristic.py` will be replaced (or extended) once Tier A lands. The PunchEvent contract may grow `velocity_3d_ms`, `direction`, and `velocity_source` fields.

# 009. Extension-cycle punch detector — precision over velocity-peak counting

- **Status**: Accepted
- **Date**: 2026-05-22
- **Phase**: 1 (bug fix to the punch detector; contract shape unchanged)

## Context

The Phase-1 `HeuristicPunchDetector` counts a punch on any wrist-velocity peak
that clears three hard gates: speed over a `1.2 m/s` threshold, now decelerating,
and ≥150 ms since the last count. The geometric checks that actually define a
punch — the arm extending forward from a chambered position, the elbow opening —
were deliberately softened to *confidence-only* nudges after they rejected real
punches, so nothing blocks a non-punch anymore.

The result is severe over-counting, confirmed on real data:

- On the one **labeled** reference session (4 true punches, saved pose parquet):
  the detector emitted **84** events — precision **0.05**, 80 false positives,
  recall 1.0, F1 0.09.
- A user's **still, no-punch** session logged **26**; a controlled **10-punch**
  session logged **39** (dominated by both-hands-same-millisecond body-sway
  fires and blips barely over the 1.2 threshold).

Diagnosis on the labeled session: real punches peak at **4–5 m/s** while
background movement sits below ~2 m/s. The `1.2 m/s` threshold is far too low,
and velocity-peak-per-frame at 30 fps with world-landmark noise produces many
spurious peaks. Extension *amplitude* alone does not separate them (the fighter
never fully retracts to a tight guard), so the discriminator must be **ballistic
speed plus a complete out-and-back excursion**.

Constraint: `capture/cv`, `capture_runner`, and the `HeuristicPunchDetector` are
Phase-1 frozen (ADR 004). But this is a genuine defect, and the fix changes only
count *values*, not the response *shape* (`punch_count` stays an int, `PunchEvent`
keys/types are unchanged), so the `/v1` contract holds per ADR 005 and the
contract tests still pass. It is therefore treated as a documented bug fix.

## Decision

Add a new `analyze.ExtensionCyclePunchDetector` and make it the **default** live
detector, selectable back to the old one via `ALION_PUNCH_DETECTOR=heuristic`.

The new detector tracks the wrist→shoulder extension as a signal and, with
hysteresis, finds each local peak and the valley (chamber) preceding it. A peak
becomes a punch only when **all** hard gates pass:

- **Ballistic speed** — peak wrist speed during the outward motion ≥
  `min_peak_velocity_ms` (default 3.0; was effectively 1.2). This is the primary
  discriminator.
- **Real travel** — excursion amplitude (peak − chamber) ≥ `min_excursion_m`.
- **Completed out-and-back** — the wrist must turn around (hysteresis) before a
  peak counts, and one count per peak.
- **Refractory** — minimum time between counts.

It is a drop-in for the live path: same `feed(frame) -> list[PunchEvent]`
interface, a `near_misses` property for parity, and the same downstream
punch-type classification and velocity refinement apply. `capture_runner`
selects it; nothing else changes. The old detector, its module, and the `/v1`
contract are untouched.

**Two implementations, kept in sync.** Live webcam capture runs pose detection
*and punch detection in the browser* (`apps/dashboard/lib/punchDetector.ts`, a
MediaPipe pipeline that bulk-uploads events via `POST /sessions/{id}/events/bulk`).
The Python `capture_runner` path is used for uploaded-video / offline
reprocessing. So the same extension-cycle algorithm is ported to TypeScript with
identical thresholds and validated with the same synthetic cases; the Python
detector is the reference. A future refactor could serve one shared spec, but
until then any threshold change must be made in *both* files.

## Validation

Re-run on the labeled session (4 true punches), same pipeline:

| Detector | Detected | TP | FP | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| HeuristicPunchDetector | 84 | 4 | 80 | 0.05 | 1.00 | 0.09 |
| ExtensionCyclePunchDetector | 7 | 3 | 4 | 0.43 | 0.75 | 0.55 |

Across 11 recorded sessions with saved pose, total detections fell from **672**
to **49** (a **93% reduction** in over-counting).

The default thresholds are a first pass tuned by hand on limited data; they are
constructor parameters and env-tunable, to be finalized once clean controlled
recordings (still + N clean punches, *with saved pose*) are available.

## Alternatives considered

- **Confidence-threshold filter on the existing detector** — rejected as a fix.
  False positives span the whole confidence range; on the still session 8 of 26
  scored ≥0.8, so filtering cannot reach the truth.
- **Offline second-pass / consensus** (the built-in `SecondPassDetector` seam) —
  not viable here: recent live sessions save no pose parquet (separate bug), so
  there is nothing to re-run after capture. The fix must live in the live path.
- **MediaPipe Hands + fist detection** (from the referenced `PUNCHES_COUNTER`
  and `BoxingWithML` repos) — rejected. Both are basic, unlicensed hobby
  projects; fist-gesture detection is unreliable on fast, motion-blurred punches
  and would require a second pose pipeline. Their one useful idea — a punch moves
  the hand toward the target — is already captured by the extension signal.

## Consequences

- **Positive**: precision-first counting; ~93% fewer false positives on real
  data; fully reversible via env var; no contract-shape change, so `/v1` and its
  locked tests are unaffected.
- **Negative / risks**: a fixed velocity threshold may under-count very soft
  punches; thresholds are not yet tuned on clean ground truth. Known edge cases
  remain — a first-punch bootstrap miss and occasional post-punch recoil
  double-counts — to be addressed with clean data.
- **Follow-ups**: fix the pose-not-saved defect (live sessions land with
  `frame_count=0` and no parquet), which blocks offline evaluation *and* the
  dissertation's RQ2 accuracy study; then finalize thresholds and consider a
  per-fighter calibration.

## Amendment (2026-05-22): direction-invariant elbow gate

Live testing surfaced a real gap: straight punches thrown *toward the camera*
were missed while side-on punches counted. A toward-camera punch travels along
the depth axis, which a monocular camera compresses, so its measured wrist
speed/travel fall under the excursion gate (the limitation ADR 003 flagged).

Added a second, **direction-invariant** trigger: the elbow-extension gate. A
jab/cross straightens the elbow regardless of facing, so a fast bent→straight of
the elbow (chamber ≤100°, extend ≥150°, within a 200 ms window) counts as a
punch even when the wrist's forward motion is invisible. Hooks/uppercuts never
fully straighten and stay with the excursion gate. Both gates share one
per-hand refractory, so a jab that trips both counts once. Added to both the
Python and TS detectors with matching parameters and unit tests (including
camera-facing and slow-reach cases). Thresholds remain first-pass, pending real
pose data.

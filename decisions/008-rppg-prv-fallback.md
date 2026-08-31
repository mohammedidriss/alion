# 008. rPPG between-rounds cardiac fallback — PRV as a distinct source, not HRV

- **Status**: Accepted
- **Date**: 2026-05-22
- **Phase**: 2 (capture band — physiological, HRV-adjacent)

## Context

Physiological monitoring in Alion depends on the Polar H10 chest strap. Not
every session has one: a fighter forgets it, a drop-in session has no strap, or
the strap loses contact. Remote photoplethysmography (rPPG) estimates pulse from
the subtle skin-colour changes of a face in ordinary video — a no-extra-hardware
fallback that reuses the camera already present for CV.

Two facts make rPPG a *fallback*, not a peer of the H10, and they must be
encoded in the design rather than left to a caller's discipline:

1. **rPPG yields PRV, not HRV.** The inter-beat interval it recovers comes from
   the blood-volume-pulse peak in video, not the ECG R-wave the H10 measures.
   Pulse-rate variability (PRV) and heart-rate variability (HRV) correlate at
   rest but diverge under motion and autonomic arousal. Writing rPPG beats into
   the HRV stream would silently corrupt RMSSD/SDNN analyses that assume ECG RR
   intervals.
2. **rPPG is motion-sensitive.** It is only trustworthy in low-motion, well-lit
   windows — i.e. *between rounds*, at rest — never during active boxing.

Constraints: an isolated capture adapter (ADR 001/004) that, per the approved
Decision 2A, defines its **own** frame handling and does **not** import
`capture.cv`'s `FrameSource`; T_0 tagging on the single `SessionClock`
(ADR 006); additive contracts that stay on `/v1` (ADR 005); synthetic/self-test
data only until Phase 8 (ADR 002).

## Decision

Model the rPPG cardiac estimate as a **distinct cardiac source** with its **own**
sample type and table, produced by its **own** isolated adapter — never merged
into or substituted for the Polar H10 HRV (`hr_sample`) stream.

- **Adapter**: new package `packages/capture/rppg/` — depends only on
  `contracts` + `common`, imports no sibling capture module (notably not
  `capture.cv`, per Decision 2A), and is added to the `import-linter`
  independence contract. Ships `estimator.py` (pure POS-projection + FFT
  band-pass + peak detection over an RGB trace; numpy lazy-imported) and
  `source.py` (windowed estimation → `PulseSample`s + its own minimal frame/ROI
  helper).
- **Contract** (additive to `contracts/events.py`): `PulseSample`
  (`session_id`, `t_ms`, `ibi_ms`, `pulse_bpm`, `quality`, `source`) and a
  `CardiacSource` literal (`rppg`). The interval field is named `ibi_ms`
  (inter-beat interval) deliberately — **not** `rr_ms` — so it is never confused
  with an ECG RR interval. Additive → **stays on `/v1`** per ADR 005.
- **Storage**: new `pulse_sample` table (`PulseSampleRow` + `PulseSampleRead` +
  `CardiacSourceEnum`, `PulseSampleRepo`), a reviewed reversible Alembic
  migration. **No rows are ever written to `hr_sample`.**
- **T_0**: each `PulseSample.t_ms = window_start_ms + beat_offset_within_window`,
  where `window_start_ms` is the SessionClock offset of the window's first frame
  (`clock.now_offset_ms()` live, or `frame_index * 1000/fps` offline). Samples
  are therefore T_0-relative like every other stream.
- **`SCHEMA_VERSION` unchanged** (Decision 1A): raw stream events only; the fused
  `SessionSummary` is untouched.
- **Advisory, rest-only.** The stream is labelled a between-rounds low-motion
  fallback; it does not replace the H10 and is not a medical measurement.

## Alternatives considered

- **Write rPPG beats into `hr_sample` as another HR source** — rejected. Conflates
  PRV with ECG-HRV; the two have different noise and validity, and pooling them
  would corrupt HRV metrics that assume RR intervals.
- **Reuse `capture.cv`'s `FrameSource` / pose frames** — rejected. Violates the
  sibling-isolation rule (Decision 2A); rPPG also needs a face/skin ROI, not
  pose landmarks.
- **Promote `FrameSource` into `contracts/` so both adapters share it** —
  deferred. Cleaner long-term, but it mutates frozen Phase-1 `capture.cv` and
  needs its own ADR.
- **Use rPPG as a primary HRV source** — rejected. Motion sensitivity makes it
  unreliable during active boxing; it is a rest-only fallback by nature.

## Consequences

- **Positive**: a physiological signal is available without a strap for low-motion
  windows; the adapter is isolated, additive, and reversible; PRV is kept
  cleanly separate from HRV so downstream analyses stay honest.
- **Negative / risks**: rPPG accuracy depends heavily on lighting, motion, and
  skin tone — a documented external-validity limit, and the reason for the
  `quality` field and the rest-only scope. No fusion consumer exists yet. Camera
  contention with CV is avoided because rPPG runs between rounds when CV capture
  is idle.
- **Follow-ups**: the composition root (`api/`) adds endpoints + `clock_for`
  wiring and a motion/quality gate that rejects high-motion windows; validating
  PRV-vs-HRV agreement at rest is a natural research question; Phase-4 fusion may
  add a cardiac-fallback block to `SessionSummary` (bump `SCHEMA_VERSION` then).

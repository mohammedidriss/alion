# 024. A visible safety boundary, "Health notes", and the roadmap kept apart

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

A second external review found that the product could look medically
authoritative: a "Medical" area, readiness labels such as "Fatigued", heart-rate
text that "flags overtraining", and wrist "impact" figures, with no boundary next
to them. AI advice already carries its notice (ADR-018), but the other outputs
did not. Planned capabilities ("Impact detection", "Cadence & fatigue") also sat
beside working ones on the IMU page, in dim text that was hard to read.

## Decision

- **One safety line** (`<SafetyBoundary>`): "Training support only — not medical
  advice. Alion can't diagnose, clear a fighter to train or fight, advise on
  return to play, or decide a stoppage; a qualified person does." It sits beside
  every readiness, heart-rate, wrist-force and health output: the HRV tab, the
  dashboard's readiness card, the gym roster's readiness, the session's HRV panel
  and per-round breakdown, the health-notes banner and the Health notes page.
- **Descriptions, not verdicts.** Readiness reads "Above / Near / Below baseline"
  (it is a z-score against the fighter's own baseline), not "Ready / Fatigued";
  an RMSSD drop "can reflect accumulated training load — a prompt to talk, not a
  verdict"; wrist "impact" is the force the fighter delivered ("Avg wrist g").
- **"Medical" is now "Health notes"** in the navigation, the page and the
  dashboard banner (the address stays `/medical`). The page says Alion doesn't
  use the notes in any score, advice or decision — true: they never reach the AI
  coach or the readiness score — and that they don't replace a doctor or a
  ringside physician. Access stays as ADR-017 set it.
- **Available now vs. research roadmap.** The IMU page lists what works (raw
  wrist streams; each punch's peak wrist force) and puts the rest under a closed
  "Research roadmap — not built yet". The HRV device list drops the unbuilt
  between-round recovery curves to a "Not built yet" line. Secondary text and
  badges there are larger and brighter.

## Consequences

- Dashboard only; no API change.
- Further plain-language renames (IMU, HRV, Datasets, Bouts) are a separate step.

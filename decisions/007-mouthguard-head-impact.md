# 007. Instrumented mouthguard — head impact as its own event type

- **Status**: Accepted
- **Date**: 2026-05-22
- **Phase**: 3 (capture band — new sensor stream, alongside IMU)

## Context

Alion measures what the athlete *does* (CV punches, IMU hand kinematics) and
their physiological *state* (HRV). It has no measurement of what the athlete
*receives* — head impact. Instrumented mouthguards (Prevent Biometrics,
Stanford MiG-class devices) are the accepted wearable for this: a 6-DOF
sensor bonded to the upper dentition streams a discrete event per impact —
peak linear acceleration, peak rotational velocity/acceleration, and impact
location — over BLE.

This is a genuinely new signal, not a variant of an existing one:

- A **punch** is a *hand* kinematic event the athlete generates. A **head
  impact** is a *head* event the athlete usually *receives* — most often from
  the opponent, not from their own punch. Folding one into the other would
  corrupt both: punch analytics would inherit impacts the fighter never
  threw, and impact analytics would be trapped inside a hand-centric schema.
- The physical quantities differ (linear g + rotational rad/s + location vs.
  wrist velocity + hand + type), so a shared row would be mostly-null on both
  sides.

Constraints: this must be a new, isolated capture adapter (ADR 001 module
boundaries, ADR 004 phase isolation); it cannot touch frozen Phase-1 code; it
must tag samples on the single `SessionClock` T_0 (ADR 006); and — because
head impact carries concussion connotations — it must stay strictly advisory
telemetry, never a diagnosis (CLAUDE.md: not a medical device).

The hardware is not yet in hand, so the adapter ships with a CSV replay /
synthetic source first (ADR 002: synthetic data only until Phase 8), matching
how the HRV stream was built ahead of the Polar H10.

## Decision

Model head impact as its **own** raw event type, stored in its **own** table,
produced by its **own** isolated adapter.

- **Adapter**: new package `packages/capture/mouthguard/` — depends only on
  `contracts` + `common`, imports no sibling capture module, and is pinned as
  mutually independent from `capture.cv` / `capture.hrv` / `capture.rppg` via a
  new `import-linter` *independence* contract. Ships `replay.py` (CSV replay +
  a pure `parse_impacts_csv()` for tests) and `device.py` (live BLE, lazy
  `bleak`), mirroring the HRV `replay.py` / `polar.py` split.
- **Contract** (additive to `contracts/events.py`): `HeadImpactEvent`
  (`session_id`, `t_ms`, `peak_linear_accel_g`, `peak_rotational_vel_rad_s`,
  `peak_rotational_accel_rad_s2 | None`, `location: ImpactLocation`,
  `device_id: str | None`, `confidence`) and an `ImpactLocation` literal
  (`front | back | left | right | top | chin`). Per ADR 005 this is additive
  (new type, new table, new endpoints) and **stays on `/v1`**.
- **Storage**: new `head_impact_event` table (`HeadImpactEventRow` +
  `HeadImpactEventRead` + `ImpactLocationEnum` in `store/models.py`,
  `HeadImpactRepo` cloned from `IMUSampleRepo`), created by a reviewed,
  reversible Alembic migration. Never written to `punch_event` or `imu_sample`.
- **T_0**: the adapter receives a `SessionClock` (fetched by the composition
  root via `clock_for(session_id)`). Live BLE impacts are OS-arrival-stamped →
  `clock.offset_from_wall(arrival)`; replay offsets are already T_0-relative.
- **`SCHEMA_VERSION` unchanged.** These are raw stream events; the fused
  `SessionSummary` contract is untouched, so its version stays `1.0.0`
  (Decision 1A). Adding a head-impact block to `SessionSummary` is deferred
  Phase-4 fusion work and will bump the version then.
- **Advisory only.** The stream is telemetry for coaching and load management,
  explicitly not a concussion diagnosis or return-to-play decision.

## Alternatives considered

- **Fold impact fields into `PunchEvent`** — rejected. Conflates a received
  head event with a thrown hand event; pollutes punch analytics with impacts
  the fighter never threw; leaves both halves of the row mostly null.
- **Store impacts as `imu_sample` rows** — rejected. The mouthguard emits
  discrete per-impact events with location, not a continuous accel/gyro
  stream; the schemas and query patterns don't match.
- **Wire into `SessionSummary` now** — deferred. Fusion is Phase 4; doing it
  here would cross a phase boundary and force a premature `SCHEMA_VERSION` bump.
- **A shared `capture.inertial` package for IMU + mouthguard** — rejected.
  Violates the one-adapter-per-package isolation rule and couples two
  independently-evolving sensors.

## Consequences

- **Positive**: the only measured head-impact signal is captured cleanly and
  safely; the adapter is fully isolated and additive; the migration is
  reversible (`downgrade` drops only the new table); no Phase-1 code or the
  `/v1` contract is touched; `make verify` guards it all.
- **Negative / risks**: precise correlation of a head impact to the specific
  punch that caused it needs sub-frame alignment — deferred to a physical sync
  gesture (tap the guard during the clap) feeding the Phase-4 `TimeAligner`;
  baseline alignment via `offset_from_wall` is coarse (~10s of ms). Real
  hardware is not yet in hand, so first data is replay/synthetic. No fusion
  consumer exists yet — the rows are captured before they are analysed.
- **Follow-ups**: the rPPG cardiac fallback is the sibling decision (ADR 008);
  Phase-4 fusion may add a head-impact block to `SessionSummary` (bump
  `SCHEMA_VERSION` then); the composition root (`api/`) adds upload/list
  endpoints and `clock_for` wiring after this adapter lands; derived
  cumulative-load metrics (impact counts, HIC-style summaries) are a later
  analyze-layer concern.

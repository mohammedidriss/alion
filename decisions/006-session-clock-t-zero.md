# 006. SessionClock — single T_0 reference for cross-modality alignment

- **Status**: Accepted
- **Date**: 2026-05-07
- **Phase**: 2 (HRV) → 3 (fusion)

## Context

Phase 2 introduces HRV alongside the existing CV pipeline. Phase 3 will
add IMU. Each modality has its own clock source today:

- CV pipeline tags `PoseFrame.t_ms` from a pipeline-internal counter.
- HRV replay reads relative offsets from a CSV.
- HRV BLE (Polar H10, arriving 2026-05-16) will produce packets stamped
  by the OS at arrival.
- IMU (TBD) will produce packets stamped at arrival.

A punch in boxing lands in 50–150 ms. If the CV clock and the HR clock
disagree by even 100 ms, "heart rate at impact" is noise. We need a
single T_0 reference that every stream tags its samples against, so
cross-modality questions ("HR at peak velocity", "RMSSD during the
last round") become deterministic arithmetic instead of best-effort
alignment.

This is a soft prerequisite that can wait until two streams actually
overlap. With H10 arriving in 9 days, that prerequisite is now
imminent — we want the contract in place before the hardware lands so
adapters integrate cleanly instead of being retrofitted under pressure.

(Origin: Gemini critical refinement #1, 2026-05-06.)

## Decision

`packages/common/time_utils.SessionClock` is the single T_0 reference
per session. It is anchored at the moment a session transitions to
`CAPTURING` and discarded when capture ends. Every adapter that
produces samples for the analyze layer MUST tag those samples with
`t_ms` offsets relative to this clock, computed via either
`now_offset_ms()` (in-process, monotonic) or `offset_from_wall(dt)`
(external timestamps).

Storage and access:

- `_session_clocks: dict[UUID, SessionClock]` lives in
  `api/services/capture_runner.py` (the composition root for active
  sessions). The CV runner anchors it; other runners fetch it via
  `clock_for(session_id)`.
- The wall-clock anchor `wall_t0` matches `Session.started_at` so any
  artifact saved with absolute timestamps can be re-aligned later.
- `monotonic_ns_t0` is for in-process precision; it is not persisted
  (process-relative; meaningless across restarts).

The CV pipeline's existing `t_ms` math is unchanged in this commit —
it already produces session-relative offsets, and changing it would
risk Phase 1 regressions. The clock simply records T_0 so future
modalities can align to the same instant. As HRV-BLE and IMU adapters
arrive, they will adopt the clock; CV may be retrofitted later if a
sub-frame reconciliation between the pipeline counter and the wall
clock is ever needed.

## Alternatives considered

- **Re-anchor every modality to its own start time** — rejected. That's
  what we have today and it does not solve the alignment problem; it
  just postpones it to ad-hoc reconciliation in `analyze`.
- **Store T_0 in the database** — rejected for `monotonic_ns_t0`
  (process-relative, useless across restarts). The wall-clock anchor is
  already in `Session.started_at`; no new column needed.
- **Build a full jitter buffer now** — rejected. We have no measured
  drift yet. Build the contract; measure first; add buffering only if
  the data demands it.

## Consequences

- **Positive**:
  - HRV-BLE driver, when it lands, gets a one-line integration:
    `t_ms = clock.offset_from_wall(packet_arrival)`.
  - Cross-modality analyses ("HR at impact") become deterministic
    arithmetic in `analyze`, not best-effort guessing.
  - The contract is documented before the hardware so adapters land
    correct on first commit instead of being retrofitted.
- **Negative / risks**:
  - The CV pipeline's `t_ms` is still pipeline-local; until it adopts
    the clock too, sub-frame alignment between CV and HR samples
    relies on the assumption that the pipeline starts within a few ms
    of capture transition (true in practice, ~5 ms). If we ever need
    sub-5 ms cross-modality alignment, CV must be retrofitted.
  - `_session_clocks` is in-process only; if the API restarts mid
    capture the clock is lost. Today this would already lose the
    capture itself, so not a new failure mode.
- **Follow-ups**:
  - Wire H10 BLE adapter to `clock_for(session_id)` when it lands.
  - Consider adopting the clock in CV pipeline if drift measurements
    show it's worth the refactor.
  - Add a `Session.t0_monotonic_ns` column ONLY if a future feature
    needs cross-process clock recovery (it doesn't today).

# 042. Stream health, gaps as missing, clipped wrist readings, camera clock drift

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The review board's first P0 was a synchronisation and graceful-degradation
engine: every stream's health known, a dropped stream treated as missing (never
as zero), and clocks aligned to within a frame. It also found that the WT901 wrist
sensors read ±16 g while elite glove peaks reach about 160 g, so Alion's "peak
force" is a floor.

## Decision

- **Stream health** (`api.services.stream_health`, `GET /v2/sessions/{id}/streams`):
  each camera, each wrist and the chest strap is OK, degraded, lost or recovering:
  - wrist: OK at ≥ 90 % of 100 Hz with a sample in the last 0.5 s; lost after 2 s
    without one or when disconnected;
  - strap: OK with a beat in the last 3 s and ≤ 5 % artifacts in the last 30
    beats (degraded "noisy contact — wet the strap"); lost after 5 s;
  - camera: OK when heard from in the last 2 s; degraded when slow or its app is
    in the background; lost after 6 s;
  - a lost stream comes back as "recovering" until it holds OK for 3 s (wrist),
    10 s (strap) or 2 s (camera).
  The wrist status now carries `drops` and `last_ms_ago`; the strap its last beat
  and recent intervals; the coordinator each camera's last-seen age. A status strip
  (■ camera, ● wrist, ♥ strap — shape and word as well as colour) shows them while
  recording and in Rest Mode.
- **Gaps are missing**: every round reports the share of it each stream covered
  (`coverage`; a gap over 0.5 s for a wrist or 3 s for the strap is uncovered). The
  rest cards turn a stream under 80 % into a fact and lower the quality of the
  facts that depend on it; the round table marks the round ◐.
- **Clipped readings**: a wrist punch whose window has an axis at ≥ 15.5 g is
  `clipped`; rounds count them, the table shows "≥ 16 g", and the force fact says
  it's a minimum (quality 0.4).
- **Camera clock drift** (`punch_fusion.sync_drift`): a Theil–Sen line through a
  camera's paired offsets against the wrists — from ≥ 40 pairs over ≥ 2 minutes —
  straightens its clock before the offset is taken, but only when the drift would
  move its punches by ≥ 40 ms across the recording. Reported per camera
  (`drift_ppm`); cross-check version 4. On the three latest real sessions no camera
  drifted enough to be corrected.

## Consequences

- `tests/unit/test_stream_health.py`, the drift test in `test_punch_fusion.py`.
- The board's ±50 ms glove-tap sync gesture isn't built: the cameras are aligned
  after the session from shared punches, which the drift fit now refines.
- A higher-range wrist sensor (±64–200 g, 400 Hz–1 kHz) is still needed to measure
  force rather than flag its floor.

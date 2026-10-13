# 025. The HRV and IMU tabs list every session's recordings

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

The HRV tab listed only sessions with a 5-minute resting baseline (an RR CSV
uploaded before warm-up): 3 of 169 sessions. The heart rate the Polar strap
records during a session never appeared there, and with no baseline the whole
tab was an empty state. The IMU tab showed the live sensors and a feature list,
but no session's wrist data. Nothing showed which sessions had no recording at
all — until ADR-023 the strap recorded only when someone pressed Connect.

## Decision

- `GET /v2/fighters/{id}/recordings` (`routes/recordings.py`, the fighter's
  training data under ADR-017) returns every recorded session — the cameras
  recorded it, or a sensor stored something — newest first, with:
  - **heart**: beats stored, span, mean and max HR, RMSSD and SDNN
    (`analyze.hrv_metrics`). Intervals outside 30–200 bpm are left out of the
    rates and variability — one dropout of a few seconds would otherwise swamp
    RMSSD — but every stored beat is counted;
  - **wrists**, per hand: samples, span, rate and peak acceleration, grouped in
    the database.
- `<SessionRecordingsCard>` on the HRV tab (heart) and the IMU tab (wrists): one
  row per session, linked to it, "N of M sessions recorded", and "No heart rate
  / wrist data recorded" on the sessions that have none; a toggle hides those.
  The HRV tab shows it even when there's no resting baseline.

## Consequences

- `tests/integration/test_api_recordings.py`.
- Sessions recorded before ADR-023 mostly show no heart rate; new ones should
  all have it while the strap is worn and paired.

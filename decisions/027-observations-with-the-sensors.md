# 027. Observations combine performance with the strap and the wrists

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

The Observations tab — its performance trend and the AI observations — read
punches only from the punch table and heart rate only from the resting baseline.
Camera training sessions store their punches in the wrist ↔ camera cross-check,
not the punch table (`multicam/complete`), so every recent session read as 0
punches there, including ones with 193 counted punches; and the heart rate and
wrist force recorded during sessions (ADR-023, ADR-025) never reached the tab.

## Decision

- **One place for a session's numbers** — `services/session_metrics.py`, used by
  `GET /fighters/{id}/performance-trend` and the AI observations. Punches come
  from where the session settled them, as its per-round breakdown does: the saved
  cross-check (counted punches, their camera speed and wrist force), else the
  punch table, else the wrist sensors alone, else none. The trend reads saved
  cross-checks only — even one from older fusion rules — and never starts a run
  (a run per old session would cost minutes); opening a session updates its own.
- **During the session**: mean and max HR and RMSSD from the strap, peak wrist
  acceleration and the counted punches' average peak force from the wrists
  (`services/sensor_summary.py`, shared with the HRV and IMU tabs).
- The score is unchanged (90th-percentile speed × punches per second × minutes);
  speed and score are left empty, not zero, when no punch speed was measured
  (wrist-only sessions), and punches per minute is 0, not huge, for a session
  with no recorded length.
- **The tab**: the trend chart adds Avg HR and Punch force lines (sessions without
  them are skipped, not drawn at zero); the tooltip and a new "Each session" table
  show everything per session, with where its punches came from; the safety line
  (ADR-024) sits under it.
- **The AI observations** get each session's punches, rate, speed and score with
  `session_mean_hr_bpm`, `session_max_hr_bpm`, `session_rmssd_ms` and
  `avg_punch_force_g`; what wasn't recorded is left out rather than sent as null.
  The prompt and its safety rules are unchanged (training only — ADR-018).

## Consequences

- `tests/integration/test_api_session_metrics.py`.
- The HRV tab's readiness-vs-performance scatter still pairs resting baselines
  with the punch table; it only has points for sessions with a resting baseline.

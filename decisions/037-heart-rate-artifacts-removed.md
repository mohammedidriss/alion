# 037. Heart-rate artifacts are removed before HRV, and noisy HRV is flagged

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

RMSSD and SDNN were computed from every beat-to-beat interval the strap sent.
One missed beat (an interval twice as long) or an extra one (two short ones) is
enough to multiply RMSSD — on a steady 20 ms signal, a single missed beat reads
as about 150 ms. The HRV tab dropped only intervals outside 30–200 bpm (ADR-025);
resting baselines, live windows and readiness took every interval as it came.
The Codex review listed heart-rate artifact handling as open.

## Decision

`analyze.hrv_metrics.clean_hrv`, used for every figure — the HRV tab's sessions,
the per-session metrics, the live 60-second window and resting baselines:

- **Removed**: intervals outside 300–2000 ms (30–200 bpm), and intervals more
  than 20 % from the median of up to 5 beats on each side (missed and extra
  beats). A real rise or fall in heart rate moves the median with it and stays.
- **RMSSD** only from differences between two kept, consecutive beats — never
  bridged across a removed one. **SDNN** and **mean HR** from the kept beats.
- **More than 5 % removed → not reliable.** The HRV tab greys RMSSD and SDNN with
  ⚠ and the share on hover, and shows how many beats were removed. A resting
  baseline upload over 5 % is refused with what to do (wet the electrodes, sit
  still, record again) — readiness compares every session to it.

Measured on the live database's 9 sessions with heart rate: 5 untouched, one
changed slightly, 3 flagged — the 13 Oct session (6 % removed) drops from
64.5 to 17.7 ms.

## Consequences

- `tests/unit/test_hrv_metrics.py`, `tests/integration/test_hrv_baseline.py`.
- Baselines already stored stay as they were stored.
- RMSSD during or right after hard rounds still reflects breathing and effort
  more than recovery; it's shown, not interpreted.

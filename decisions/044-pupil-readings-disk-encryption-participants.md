# 044. Pupil readings as entered, the disk's encryption shown, scores per person

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

Three smaller items from the review board: a traceable field for handheld
pupillometry (V4) with no automatic interpretation; encryption at rest as an MVP
blocker for health data (Alion's database encryption is deferred, ADR-002); and
independent multi-fighter validation as the competitive opening.

## Decision

- **Pupil readings** (`pupil_reading`; `GET/POST /fighters/{id}/pupil-readings`):
  eye, NPi and/or size, when, room light, device and when in the session — as the
  device showed them. Health data under the medical access rule: the fighter and
  their coaches only, every read logged. No thresholds, no flags, no
  interpretation; the card on Health notes says so.
- **Disk encryption** (`api.services.disk_encryption`): `fdesetup status` on macOS
  (read-only, no admin rights), cached 10 minutes; the privacy page says the disk is
  encrypted, or that whoever runs Alion should turn FileVault on. Alion changes no
  system setting. Database encryption (SQLCipher) stays a separate decision.
- **Scores per participant**: the camera and wrist type models, when trained on
  takes from two or more participants, also score each person with a model that
  never saw them (`held_out_participants`, with a per-participant accuracy). With
  one participant, as now, it is None — the number to watch once other fighters
  are recorded.

## Consequences

- `tests/integration/test_pupil_and_disk.py`; the two-person tests in the camera
  and wrist type model suites.
- This computer: FileVault is on.

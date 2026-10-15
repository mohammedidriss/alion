# 056. Recordings are never deleted

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6

## Context

"Delete profile" erased the fighter and every session with its heart-rate,
wrist-sensor and punch data (while leaving files and other records behind, and
its warning named things it didn't delete). Deleting a session erased its video,
pose, clips and sensor data; "Delete" during a recording told the cameras to drop
their clips; deleting a dataset take removed its folder. Listing sessions also
purged "empty" pending sessions — including ones that recorded only heart rate
or wrist sensors. The owner decided (15 Oct 2026) that recordings are never
deleted, for anyone, and that a way to delete data will be designed later; and
that deleting a profile offers keeping the recordings or deleting the login only.

## Decision

- **Deleting a profile** (`DELETE /fighters/{id}`) keeps the recordings: the
  profile (`fighter.removed_at`) — and its login, if it has one — goes out of
  every list and every view but researchers'; its gyms, squads, coaches and
  physicians let it go (history kept). An administrator restores it
  (`POST /fighters/{id}/restore`; the login on the People page).
- **Deleting the login only** (`POST /fighters/{id}/remove-account`, ADR-048):
  nobody signs in to it; the profile and its recordings stay as they are.
- **Who**: a profile someone signs in to is deleted by that fighter or an
  administrator; one nobody signs in to, by whoever may change it. A
  researcher's own account isn't deleted from itself, so the study is never
  locked out. `GET /fighters/{id}/removal` says what the viewer may do; the
  profile page and a fighter's Profile tab ask with both choices.
- **Deleting a session** (`DELETE /sessions/{id}`) hides it (`session.removed_at`)
  and keeps the recording; a capture still recording into it stops as Stop does —
  the cameras upload their clips, the sensors save. Researchers list deleted
  sessions ("deleted too") and restore them (`POST /sessions/{id}/restore`).
- **Deleting a dataset take** discards it — out of the dataset and its export —
  and keeps its folder; its face-blurred copies, made from the original, go.
- **Purging empty pending sessions** skips any session with heart-rate,
  wrist-sensor or punch data.
- Deleted profiles and sessions still teach the models (ADR-047, ADR-051).
- Migration `e3a5c7e9b1d4`.

## Consequences

- `tests/integration/test_recordings_kept.py`; the session, take and fighter
  tests follow the new rule.
- Unchanged, and still deleting: a participant's withdrawal from a dataset (the
  terms promise it, section 9), and a file someone attached to a session.
- Deleting data for real waits for the owner's design.

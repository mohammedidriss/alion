# 054. Profiles are edited on the profile page, not the dashboard

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6

## Context

A fighter's dashboard carried "Edit profile" and "Delete profile" buttons and a
large "Your gym" panel. The owner asked (15 Oct 2026) that the dashboard only
show, and that all editing and changes happen on the profile page.

## Decision

- **The dashboard** no longer edits, deletes or answers anything. A gym waiting
  for an answer shows as one line linking to the profile page.
- **The profile page** (`/profile`, your own account) holds the gym invitations,
  "Your gym" with Leave, and — for a researcher's own fighter profile, as the
  dashboard showed it — Delete profile.
- **Someone else's fighter profile** is edited, or deleted, on that fighter's new
  **Profile** tab (`/fighters/{id}/profile`), for those the dashboard showed the
  buttons to: their coaches, their gym, researchers and admins. A fighter's own
  Profile tab opens the profile page.
- The edit form and the delete confirmation are shared components
  (`FighterEditModal`, `ConfirmModal`).

## Consequences

- Since ADR-056, deleting a profile keeps its recordings, and offers deleting the
  login only.

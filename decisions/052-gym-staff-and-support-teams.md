# 052. Gym staff, and a fighter's support team

- **Status**: Accepted — step 2 of the gym workflow (ADR-050)
- **Date**: 2026-10-14
- **Phase**: 6

## Context

A manager account was tied to one gym through its manager profile, a coach had a
single gym field (or a coach row in the gym's membership list), and nobody could
be a gym's owner or head coach. Coaches joined a gym the moment a manager added
them, any coach could be assigned to any fighter, and a coach link didn't record
how it was made — so when someone left a gym (ADR-050, step 1), the links that
ran through it could only be guessed.

## Decision

- **One staff list** (`gym_staff`, migration `a3c5e7b9d1f3`): a gym, a person (an
  account, and their coach profile for the coaching roles), a role at that gym —
  owner, manager, head coach or coach — and a status: invited, active, declined,
  left. One person can hold several roles and work at several gyms; a role is
  not an account type (a coach account can own a gym).
- **Carried over**: a manager with an account becomes the gym's owner (its first
  manager) or a manager; a coach whose profile names a gym, or who had a coach
  membership there, becomes a coach — that membership row is marked left. On the
  live data: mhd@alion.ai owns ChamionOne.
- **Joining**: owners and managers invite by account email, or a coach by System
  ID (`POST /gyms/{id}/staff`); the person accepts or declines on their profile
  page, their coach page or the gym dashboard (`/v2/my-staff`). Adding a coach on
  the Members page invites them to the staff the same way. A coach profile
  nobody signs in to, a coach account the gym makes, and someone adding
  themselves join at once. Signing up with a new gym makes you its owner
  (ADR-030). Only an owner (or an administrator) adds or removes an owner, and a
  gym keeps at least one.
- **Access, from the staff list** (`access.Viewer`):
  - owners and managers — the gym's members, staff and settings, and its
    fighters' training (as gym managers had);
  - head coaches — the gym's fighters' training, and its coaches onto their
    support teams;
  - coaches — the gym's fighters' profiles, and the fighters assigned to them.
  The gym's pages, and "which gym do I manage", work for anyone who owns or
  manages a gym, whatever their account type; their menu says so
  (`/auth/me` → `gym_roles`).
- **A fighter's support team**: a coach link now has a type that includes non-
  coaching help (assistant coach, physiotherapist, manager, besides nutrition,
  cutman, mental…), records who made it (`granted_by`) and the gym it came
  through (`source_gym_id`). The fighter adds anyone, as their own. A gym's
  owner, manager or head coach — or a coach adding a colleague — adds only
  someone on that gym's coaching staff, and the link is the gym's: it ends when
  the fighter leaves the gym or the coach leaves its staff. A link made before
  this (no maker recorded) counts as the gym's when its coach is the gym's staff
  and its fighter a member — ending it errs on the side of privacy. Health notes
  are still the fighter's to share, link by link (ADR-046).
- Everyone who leads a gym — owners, managers, head coaches — is who the
  fighter's invitation and Privacy & consent page say will see their training.

## Consequences

- `tests/integration/test_gym_staff.py`; the gym workflow and invitation tests
  follow the new rules (a coach is invited and accepts).
- Every support-team member sees the fighter's training as coaches do; narrower
  access by type (a cutman seeing only bout details) isn't built.
- The manager profile (`gym_manager`) still grants its gym, alongside the staff
  list; new gyms and new managers also get a staff row.
- Step 3, squads, builds on this list.

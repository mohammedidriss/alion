# 030. Gym managers sign up with a new gym of their own

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

ADR-017 limited sign-up to fighters, coaches and referees: a gym manager has to
belong to a gym, and a gym's managers see its members' training data, so signing
up into an existing gym would let a stranger in. The sign-up form still offered
"Gym Manager", and the API refused it every time. The role stays — gym owners
should be able to start on their own.

## Decision

- **Gym manager is a sign-up role again, with a gym name.** Signing up as a gym
  manager creates a new gym with that name and makes the account its manager
  (`gym_name` on `/auth/register`; refused with 422 when missing, before any
  account is made). The form shows a "Gym name" field for that role and says that
  managing a gym already on Alion is set up by an administrator.
- Nobody can sign up into an existing gym: the new manager's access (ADR-017) is
  their own new gym — empty until people join it.
- Admins are still made only by an admin.

## Consequences

- `tests/integration/test_access.py`: the gym is created and theirs, no gym name
  is refused, and another gym's members stay closed to them.
- Still as before ADR-030, now more exposed: a gym's managers and coaches can add
  a fighter to the gym by the fighter's System ID, which opens that fighter's
  training data to them. The ID is long and random — an invitation the fighter
  shares — but a confirmation from the fighter would be the safer next step.

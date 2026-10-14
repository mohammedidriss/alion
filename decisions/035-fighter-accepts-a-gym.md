# 035. A fighter accepts a gym before it sees their training

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

A gym's managers see its fighters' training data (ADR-017). Until now a gym's
manager or coach could add any fighter by System ID, and that alone opened the
fighter's training to the gym. ADR-030 named the fix: the fighter confirms.

## Decision

- **Adding a fighter to a gym is an invitation** (`invited`, a new membership
  status — the column is a string, no migration). By System ID
  (`/gyms/{id}/members/import`) or by profile (`/gyms/{id}/members`), the
  fighter's profile isn't moved to the gym and the gym's managers see nothing of
  their training until they accept. The invitation records who sent it.
- **The fighter answers** (`/v2/gym-invitations`): an "A gym wants to add you"
  card on their own page and on Privacy & consent, naming the gym, who invited
  them and the managers who'd see their data. Accept → `active`, their gym is set
  as before; Decline → `declined`.
- **The gym can't switch it on itself**: an `invited`, `declined` or `left`
  fighter membership can only be cancelled by the gym, not made active, trial,
  frozen or suspended. A declined or departed fighter can be invited again (the
  same row), and accepts again.
- **Access counts accepted memberships only** (`access.gym_fighters`): a fighter
  who left, or was invited back and hasn't accepted, is out even if their profile
  still names the gym.
- **Unchanged**: coaches added by System ID join at once (a coach's own data
  isn't opened); fighter accounts and profiles a gym creates itself join at once;
  existing memberships stay as they are.
- The gym's members page lists the invitations "Waiting for the fighter".

## Consequences

- `tests/integration/test_gym_invitations.py`; `test_access.py` updated (the gym
  sees the fighter's session only after the invitation is accepted).
- A gym can still invite anyone whose System ID it has; the fighter can say no.

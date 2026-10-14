# 048. Removing an account keeps the person's records

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The admin People page's Delete removed only the login row. The person's profile,
sessions and records stayed, so they showed up again as a profile without a
login, and creating the email again gave them a second, empty profile. The owner
asked (14 Oct 2026) whether that was by design; it wasn't. The data can't simply
go with the account either: recorded sessions are training data (ADR-047), and
records are kept rather than hard-deleted.

## Decision

`DELETE /auth/admin/users/{id}` now **removes** the account:

- it can't sign in, and tokens it holds stop working (`is_active` false);
- its email becomes `removed-{id}@removed.invalid`, so the address is free for a
  new account; the address it had is kept (`user.removed_email`, with
  `removed_at`, `removed_by`; migration `e9b1d3f5a7c9`);
- its current ties end, their history kept: a coach's fighters, a fighter's
  coaches and physicians, a physician's fighters;
- the profile, sessions and records stay.

`POST /auth/admin/users/{id}/restore` brings it back with its email, unless a new
account has taken that email; the ties it had are added again by hand. Other
admin actions refuse a removed account until it is restored. Nobody removes their
own account, and only a researcher removes a researcher's.

The People page says Remove (and Delete only for a profile that has no login),
hides removed accounts behind "Show removed", and offers Restore. Its create
form takes every role, physician included; the Coaches and Fighters pages open
it with the role chosen ("+ New coach", "+ New fighter").

## Consequences

- `tests/integration/test_remove_account.py`.
- A removed coach's profile can still be picked as a coach; it can't sign in, so
  it sees nothing.
- Deleting a profile that has no login is unchanged (a hard delete).

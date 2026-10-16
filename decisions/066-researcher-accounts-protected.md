# 066. A researcher's account is protected

- **Status**: Accepted
- **Date**: 2026-10-16
- **Phase**: 6
- **Amends**: ADR-048 (removing accounts), ADR-056 (deleting profiles)

## Context

The owner asked (16 Oct 2026) that `mohamad@alion.ai`, the researcher who runs the
study, be protected and impossible to remove. Before this, another researcher
could remove a researcher's account, a researcher could delete their own
training profile, and with it their login (ADR-056), and an administrator could
disable it. Only the system administrator (commit 9ddeaa2) was fully protected.

## Decision

- **An account on the researchers list (`ALION_RESEARCHERS`) is protected like the
  system administrator's.** Nobody can:
  - remove it, whether directly, through "delete the login", or by deleting its
    training profile, which takes the login along;
  - disable it;
  - give it another role.

  That covers the system administrator, another researcher and the account
  itself.
- **To retire a researcher, take them off the list** on the server first. That
  needs the server's settings, which nobody can change from the app. The
  account is then an ordinary one again.
- The People page shows 🔒 Protected in place of Disable and Remove, and locks the
  role. A researcher's training profile offers no delete.
- Everything else still works: a researcher changes their own name, password and
  photo, and edits their training profile.

## Consequences

- `test_researcher_account.py`: neither the system administrator, another
  researcher nor the account itself can remove, disable, demote, or delete the
  training profile of a listed researcher; the People page marks it protected.
  Taken off the list, a researcher can be changed to another role.
- "Only a researcher removes a researcher" (ADR-048) is replaced: nobody removes
  one while they're on the list.

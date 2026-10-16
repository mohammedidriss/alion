# 065. A researcher keeps their own training

- **Status**: Accepted
- **Date**: 2026-10-16
- **Phase**: 6
- **Amends**: ADR-062 (becoming a researcher no longer unlinks a fighter profile)

## Context

ADR-062 made `mohamad@alion.ai` a researcher account and unlinked it from the
fighter profile "Mohamad Idriss". The profile and its 166 sessions stayed, but
with nobody signed in to it. The next day the owner reported that the account
"cannot see the HRV, IMU, training sessions and all the other tabs", which had
been visible the day before.

The fighter tabs show on a fighter's own pages (`/fighters/{id}/…`). As a
fighter, the account's home was that page; as a researcher with no profile its
home became `/profile`. The tabs were still reachable through All fighters, but
they were no longer the account's own.

## Decision

- **Becoming a researcher keeps a fighter profile** the account had, as the
  researcher's own training. Any other kind of profile is still let go. Going
  back to fighter keeps it; to coach or referee gives a new profile, as before.
- **Home is that training**, with all its tabs, when a researcher has one. A
  "Researcher page" menu item opens `/profile`. The researcher card there links
  to "Your training" and to the research areas. A researcher without one keeps
  `/profile` as home.
- **The profile is someone's**: it counts as signed in to (by fighter or
  researcher accounts), so its coach can't delete it as an unclaimed profile.
  Removing the researcher's account ends that profile's coach links, as a
  fighter's would. Access treats it as the account's own fighter
  (`Viewer.own_fighter`). The People page lists the person once, as a
  researcher, with their training.
- `mohamad@alion.ai` is linked to "Mohamad Idriss" again.

## Consequences

- `test_researcher_account.py`: becoming a researcher keeps the fighter profile
  linked, with its session readable. The profile counts as signed in to. The
  People page lists one researcher entry. Going back to coach gives a new
  profile.
- The researcher's own page stays a researcher's: no fighter fields. Stance,
  weight and health notes are on the training profile's own tabs.

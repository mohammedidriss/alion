# 062. A researcher has an account of their own, not a fighter's

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6
- **Amended by**: ADR-064 — fixes from the full review

## Context

Research access comes from the `ALION_RESEARCHERS` list (ADR-017, ADR-046), on
top of whatever the account is. The researcher's account, `mohamad@alion.ai`,
was a fighter account linked to the fighter profile "Mohamad Idriss". That
profile holds 166 sessions, a coach assignment, and its owner's place as
participant F-0001 in two datasets, with consent "self". The owner said
(15 Oct 2026) that the researcher should have a profile of their own, not a
fighter's.

## Decision

- **A researcher account type** (`UserRole.RESEARCHER`), like a physician's or an
  administrator's: the account is the profile, with no profile table and no
  migration (the role column is free text).
- **Only for a listed email**: creating a researcher account, or changing an
  account to one, is refused (409) unless its email is on the researchers list.
  The list still grants the access; an account taken off the list keeps the role
  and loses the access, and its page says so. Nobody signs up as a researcher.
  The system administrator is never made one (its guard, commit 9ddeaa2).
- **Becoming a researcher unlinks the old profile**: the account's link to its
  profile ends; the profile — a fighter's, with all its recordings, coach
  assignments and dataset participation — stays exactly as it was, signed in to
  by nobody. The researcher, who sees every fighter, finds it under All fighters
  and records it like any participant's. The dataset consent is stored on the
  participant, so "self" still lets its takes be recorded.
- **Going back**: an account changed from researcher to a role with a profile
  gets a new one, as at sign-up; it isn't re-linked to the old profile.
- **Their page**: a researcher's home is `/profile` — their name, email and
  password, and a Researcher section with the research areas (All fighters,
  Datasets, AI models, Study, People). The People page lists the account as a
  researcher and the old fighter profile on its own.

## Consequences

- `test_researcher_account.py`: a listed fighter becomes a researcher, and their
  fighter profile and session stay, with no account; an unlisted email is
  refused, on create and on change; nobody signs up as one; the system
  administrator is never made one; going back to coach gives a new profile.
- A fighter profile nobody signs in to can be deleted by its coach (ADR-056); its
  recordings are kept either way.
- `mohamad@alion.ai` is changed to a researcher through the People page's own
  update, after this is applied.

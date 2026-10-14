# 046. Roles: an all-access researcher, physicians, health notes the fighter shares

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

Tabs were missing: each account had one role and the menu came from it alone, so
the researcher (a fighter account on the ALION_RESEARCHERS list) saw neither the
administration pages nor other fighters' tabs. There was no physician role, every
coach saw a fighter's health notes, and model training details (versions,
accuracy, detector tools) showed to everyone. The owner decided (14 Oct 2026,
after weighing a stricter design from an external review) that the researcher
should see and do everything, that recorded sessions train the models without an
opt-in, and that nobody else should see anything about model training.

## Decision

- **The researcher** (ALION_RESEARCHERS) can see and change every fighter's data,
  health notes included, and has every administrator power (`Viewer.can`,
  `visible_fighters`, the coach, bout and gym rules, `_require_admin`). Every
  health-note read is still logged, by role.
- **Physicians** (new role, self sign-up): a fighter adds a physician by account
  email on their Team page (`/fighters/{id}/physicians`, `physician_assignment`);
  the physician then reads the fighter's training data and reads and writes their
  health notes, and lists their fighters on `/physician`. Removing one keeps the
  history. Only the fighter (or the researcher) chooses.
- **Coaches see health notes only when the fighter shares them**
  (`coach_assignment.health_access`, a checkbox on the Team page). Coaches assigned
  before this keep the access they had; new ones start without. Only the fighter
  (or the researcher) sets it.
- **The menu comes from permissions** (`lib/nav.ts`), one place for the sidebar and
  the phone bars: the researcher gets their own section, Research (all fighters,
  datasets, study, AI model, backends) and Administration; the Study tab shows only
  to researchers, enrolled reviewers and RQ1 raters; physicians, referees and
  gym managers get their own homes. `/auth/me` says `is_reviewer` and
  `is_rq1_rater`.
- **Model details are for researchers and admins only**: model versions and
  accuracy, the detector comparison, the labels evaluation, the RQ2 condition and
  badge, the synthetic wrist stream, how a rest card was written.
- **Disclosed**: terms draft-3 say who can see what — the researcher all data,
  health notes included, with every look logged — and that recordings are used to
  develop the platform's models; the privacy page's table says the same and names
  each fighter's physicians and the coaches they share health notes with.
- Migration `d7f9b1c3e5a7`.

## Consequences

- `tests/integration/test_roles.py`; `test_access.py` updated (a new coach sees
  health notes only after the fighter shares them).
- Everyone accepts the terms again (draft-3).
- Not built: several roles per account (the researcher keeps one profile, their
  fighter's) and a role-to-permission table with scopes; the rules live in
  `access.Viewer` and `lib/nav.ts`.

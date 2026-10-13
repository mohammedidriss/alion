# 017. Record-level access control — enforced by the API, on every route

- **Status**: Accepted (part 1; part 2 added the same day)
- **Date**: 2026-10-13
- **Phase**: 6

## Context

An audit (and an external review) found that the API checked *that* someone was
signed in, never *whose* data they asked for. Any account — a fighter's
included — could read or change any other fighter's medical record, sessions,
video, heart rate and notes, export or withdraw dataset participants, and make
itself any fighter's coach. The dashboard hid some pages by role; the API
didn't. Worse: anyone could sign up as an admin, the referee routes had no
login at all, and two upload paths took `../` in file names.

The researcher's choices: research datasets for named researchers only; admins
manage accounts, never training or medical data; gym managers see their gym's
training data, not medical; medical records stay on, locked down and logged.

## Decision

**One policy, applied to every route.** `api/access.py` holds the rules;
`access.guard` is an app-wide dependency (`FastAPI(dependencies=…)`). It reads
the record a route addresses from its path — `{fighter_id}`, `{session_id}`,
`{take_id}`, `{dataset_id}`, `{bout_id}`, `{coach_id}`, `{gym_id}`,
`{manager_id}`, `{referee_id}`, or a `/takes`/`/datasets` path — and applies its
rule. A route added later is covered without anyone remembering to. The guard
only adds rules on top of authentication: with nobody signed in it does nothing,
and the route's own check (a login, a capture join token) decides.

| Data about fighter F | Who |
|---|---|
| basic profile (read) | F, F's coaches, F's gym managers, coaches at F's gym, researchers, admins |
| basic profile (change, coach assignments) | F, F's coaches, F's gym managers, admins |
| training data (read): sessions, video, heart rate, wrist sensors, notes, weigh-ins | F, F's coaches, F's gym managers |
| training data (change) | F, F's coaches |
| medical records | F, F's coaches — **every access, and every refusal, logged** |
| research datasets, takes, export, training, blurring, withdrawal | researchers only (`ALION_RESEARCHERS`) |

"F's coaches" have a current `CoachAssignment`; "F's gym managers" manage a gym F
belongs to and hasn't left. Bouts are open to whoever may see either corner, and
list only the corner sessions the viewer may see. List and create routes filter
with `access.visible_fighters` / `Viewer.require`: a coach who adds a fighter
becomes their coach; a gym manager's new fighter joins their gym.

Also in this change:

- **Sign-up** is limited to fighter, coach and referee; admins and gym managers
  are made by an admin.
- **Referees** require a sign-in; only admins add them, only they or an admin
  change them. New coach profiles: admins and gym managers; new gyms and gym
  managers: admins.
- **File names**: attachments keep only the base name; phone device ids must be
  letters, digits, `-` and `_` (checked at the API and where take paths are built).
- **Ownership bugs**: deleting a weigh-in, removing a bout corner and checking out
  of a gym now check the record belongs to the fighter / bout / gym in the path.
- **Medical access log**: table `access_log` (migration `c7f1a9e3b5d2`) — account,
  role, fighter, route, read/write, allowed; never the content.
  `GET /fighters/{id}/medical/access-log` shows it to whoever may see the records.
- **Dashboard**: the Datasets tab shows for researchers only (`is_researcher` on
  `/auth/me`).

## Alternatives considered

- **A check written into each route.** ~200 handlers; one forgotten route reopens
  the hole, and new routes start unguarded.
- **404 instead of 403 for records you may not see.** Hides that a record exists,
  but UUIDs aren't guessable and a clear 403 is easier to support; revisit if ids
  ever become sequential.
- **Rely on the dashboard hiding pages.** Anyone can call the API directly.

## Consequences

- `tests/integration/test_access.py` covers each role; the shared test account
  is now a coach who is also a researcher (`admin_client` for admin-only routes).
- The researcher's own account must be listed in `ALION_RESEARCHERS` in `.env`,
  or the datasets close to them too.
- Still open: coach and gym-manager listings aren't scoped beyond gym managers.

## Part 2 — signed, expiring links

Some things a browser loads can't carry a login header: an `<img>` (the live
camera preview, profile photos), an `EventSource` (the live heart-rate stream),
and a phone that joined by QR. They were open to anyone who had the URL. They now
take a signed link (`api/services/signed.py`): `{expiry}.{HMAC(secret,
purpose|resource|expiry)}` — bound to what it opens, checked without storing
anything (so it survives restarts), impossible to stretch or repoint.

| What | How it's opened now | Lasts |
|---|---|---|
| live preview, live heart rate | `GET /sessions/{id}/live-links` (signed in, access-checked) → `?t=` links | 6 h |
| profile photos | `GET /auth/photo-pass` → `?t=` on every photo link (the dashboard adds it, renews every 6 h) | 24 h |
| a phone's capture join link | signed per capture; renewed by join-info / the studio when under 2 h are left; the old never-expiring kind no longer works | 24 h |
| a phone's studio link | signed for the coach + a per-coach nonce; **Unlink all phones** changes the nonce and voids every link | 30 days |

`tests/integration/test_signed_links.py` covers each.

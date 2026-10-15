# 055. Joining a gym: a code, approval, rules, an emergency contact; camps and attendance

- **Status**: Accepted — step 4 of the gym workflow (ADR-050)
- **Date**: 2026-10-15
- **Phase**: 6

## Context

A fighter joined a gym only when the gym invited them (ADR-035). A gym had no
rules to agree to, nothing recorded who to call in an emergency, a fight camp
wasn't tied to its fight, and attendance wasn't seen by squad.

## Decision

- **A join code** (`gym.join_code`; migration `d1f3a5c7e9b2`): the gym's owners and
  managers make one, replace it (the old one stops working) or turn it off, on
  the Members page — with its link and QR code. A fighter opens the link, or types
  the code on their profile page, and **asks to join** (`/v2/join/{code}`): a new
  membership status, `applied`. The gym sees nothing of their training until it
  **approves** — on trial, or straight in (`/gyms/{id}/members/{m}/approve`) — or
  rejects; trial members are made active as before. The fighter can withdraw. A
  fighter the gym invited who uses the code joins at once; the gym can't invite
  someone waiting for its answer.
- **The gym's rules** (`gym.rules`, `gym.rules_version`), written on the gym
  dashboard: joining — accepting an invitation or asking with the code — means
  accepting them when there are any, and the version accepted is recorded on the
  membership. Changing them raises the version: the fighter sees the new rules
  under "Your gym" on their profile page and accepts them; the Members page shows
  who hasn't.
- **An emergency contact** on the fighter's profile (name, phone, relation),
  asked when joining with a code and edited on the profile page; seen by those
  who see the profile — their coaches, their gym's staff, their physicians — and
  listed on Privacy & consent. The Members page shows who has none.
- **A camp's bout** (`squad.bout_id`): a fight camp can name its bout; it ends on
  the bout's day unless a last day is given.
- **Attendance by squad**: squads show how many of their fighters checked in at
  the gym this week, next to who trained.

## Consequences

- `tests/integration/test_gym_joining.py`.
- Setting rules for the first time asks every current member to accept them.
- The emergency contact is asked, not required, when accepting an invitation.

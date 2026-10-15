# 053. Squads within a gym

- **Status**: Accepted — step 3 of the gym workflow (ADR-050)
- **Date**: 2026-10-15
- **Phase**: 6

## Context

A gym was one list of members: nothing grouped fighters into a competition team,
a class or a fight camp, and coaches got a fighter only one by one (ADR-052).

## Decision

- **Squads** (`squad`, `squad_member`, `squad_staff`; migration `c5e7a9b1d3f5`):
  a name, a kind — competition team, class, fight camp, other — a level, and
  optional start and end dates (a camp's last day). Its fighters are the gym's
  accepted members; one of a fighter's squads can be their main one. Its coaches
  are the gym's coaching staff (ADR-052), as coach or head coach.
- **Who runs them**: the gym's owners, managers and head coaches — create,
  change, archive, put fighters and coaches on and off (`/gyms/{id}/squads`,
  `/squads/{id}/…`). A fighter can make a squad their main one, or leave it.
- **Access**: a squad coach sees the squad's fighters' training — as a coach
  with an assignment does — while both are on it and the squad is open: not
  archived, not past its end date. Health notes stay the fighter's to share
  (ADR-046). Leaving the gym ends a fighter's squad places; leaving its coaching
  staff ends a coach's.
- **Sessions record their gym and squad** (`session.gym_id`, `session.squad_id`):
  the squad given when it's opened, else the fighter's main squad; existing
  sessions have neither.
- **Where it shows**: a Squads page for the gym's owners, managers and head
  coaches (in the menu); a fighter's squads on their Team page; a coach's squads
  with their fighters on their own page; "Squads this week" on the gym dashboard
  — who trained and how many sessions were trained with the squad, for those who
  may see the fighters' training.

## Consequences

- `tests/integration/test_squads.py`.
- Choosing a squad when starting a session isn't in the session screens yet:
  the main squad is used.
- Tying a camp to a bout is step 4.

# ADR-069 — The fight card

Status: Accepted · 2026-10-17

## Context

A fight (ADR-011) only had a label, a date, a venue and its rounds. Starting one
picked two fighters and nothing else. A boxing broadcast presents every fight
with much more, and the researcher wants the same:

- **Tale of the tape**, per fighter: record (W-L-D, KOs), age, height, reach,
  weight, stance, nationality or hometown, and often the belts held.
- **What's at stake**: a title fight names its sanctioning bodies (WBA, WBC, IBF,
  WBO; The Ring's lineal belt; the IBO; regional titles) and the kind of belt
  (world, the WBA's super and regular, interim, eliminator). Otherwise it's a
  professional non-title fight, an amateur bout, an exhibition or a friendly.
- **The weight**: the division (or an agreed catchweight) and each fighter's
  official weigh-in. A fighter who misses weight can't win the title.
- **The event**: name, arena, city and country, date and time; the scheduled
  rounds.
- **The officials** (referee, three judges) and the **promotion** (promoter,
  broadcaster).

## Decision

- The fighters' facts stay on their **profiles**: they're the same in every
  fight. The new-fight page and the fight page show them side by side as a tale of
  the tape (`TaleOfTheTape`). Anything missing or wrong can be filled in right
  there and is saved to the profile.
- The fight's own facts go on the **bout**: `fight_type`, `titles`
  ([{body, kind}]), `event_name`, `venue`, `city`, `country`, `scheduled_at`,
  `weight_class` / `weight_limit_kg` (a division's limit is filled in; a
  catchweight is entered), `red_weigh_in_kg` / `blue_weigh_in_kg`, `referee`,
  `judges` (≤ 3), `promoter`, `broadcaster`. Migration `a7c9e1b3d5f8`.
- Rules:
  - belts belong to title fights only, and a title fight needs at least one;
  - switching a fight to non-title takes its belts off the line;
  - unknown bodies, belt kinds or divisions are refused.
- `GET /bouts/options` lists:
  - the kinds of fight, with their usual rounds: title 12 × 3 min, pro 8 × 3,
    amateur 3 × 3, exhibition 6 × 2, sparring 3 × 3;
  - the sanctioning bodies and belt kinds;
  - the divisions with their limits in lb and kg.
- `PATCH /bouts/{id}` edits the card. Weigh-ins usually come the day before, and
  officials are often named late.
- `DELETE /bouts/{id}` deletes a fight **from view** (ADR-056):
  - the fight and both corners' sessions are hidden;
  - a running capture stops as Stop does;
  - every recording stays.

  `BoutRepo.get` treats a deleted fight as absent, so the camera studio
  (ADR-063) does too.

## Consequences

- Fights created before this have the defaults: a professional non-title fight
  with no card details.
- The 5 test fights that existed were deleted for good on 2026-10-17, at the
  researcher's request. None had recordings. A database backup taken first is
  `data/alion-backup-2026-10-17-before-fight-delete.db`.

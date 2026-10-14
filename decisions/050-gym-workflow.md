# 050. The gym workflow: organisation, staff, support teams, squads

- **Status**: Accepted — step 1 built; steps 2–4 planned
- **Date**: 2026-10-14
- **Phase**: 6

## Context

A gym was one flat list of members. A manager account was tied to one gym, a
coach had a single gym field (empty for both live coaches), nothing grouped
fighters into squads, and any coach could be assigned to any fighter. Fighters
were told they could leave a gym but had no way to; leaving, or a coach leaving,
didn't end the coach links made through the gym, so a gym coach kept seeing a
departed fighter's training. The owner asked (14 Oct 2026) for a full gym
workflow, compared my design with one from an external review, and chose:
roles scoped to a gym rather than several roles per account; support teams that
include non-coaches; no minors (ADR-051); no payments.

## Decision

Three kinds of "team", kept apart:

1. **The gym** — an organisation with staff, each with a role *at that gym*:
   owner, manager, head coach, coach. One person can hold several (the owner is
   often the head coach), and a coach can work at several gyms. A staff role is
   not an account type: a coach account can manage a gym.
2. **Squads** — groups within a gym (competition team, amateur squad, class, or
   a fight camp with an end date tied to a bout): a head coach, squad coaches,
   fighters (one squad marked the fighter's main one). A squad coach sees the
   squad's fighters' training while both are on it; health notes still only
   when the fighter shares them (ADR-046).
3. **A fighter's support team** — the people working with one fighter: head
   coach, assistant, strength coach, nutritionist, physiotherapist, cutman,
   manager (physicians stay as ADR-046 has them). Each link records its type,
   who granted it, and whether it came through a gym or from the fighter.

Joining: the gym invites (ADR-035), the fighter asks with the gym's join code
(an "applied" state the gym approves), or the gym creates a walk-in account who
accepts the terms at first sign-in. Leaving ends, from that day, the gym's
access, the squad places and the links made through the gym; the fighter's own
support team, physicians and data stay, and sessions never move to a new gym.

### Steps

1. **Fix what's broken** (built here):
   - a fighter leaves a gym on their own (`GET /v2/my-gyms`,
     `POST /v2/my-gyms/{id}/leave`; "Your gym" card on their page and on Privacy
     & consent);
   - leaving a gym — the fighter's choice, or the gym's — ends the coach links
     that ran through it (`GymRepo._end_ties`): a fighter's with the gym's
     coaches, a coach's with the gym's fighters; the profile stops naming the
     gym. Until step 2 records where a link came from, a fighter who leaves
     also ends a link with that gym's coach they added themselves;
   - only active or trial members check in;
   - "+ Add Gym" shows to administrators only (a manager's gym comes with their
     sign-up, ADR-030);
   - migration `f1a3c5e7b9d1` ends memberships and coach links whose person no
     longer exists — on the live data, 3 memberships and the 5 coach links.
2. **Gym staff and support teams**: one staff list (gym, person, role, status,
   invited by) with invitations to accept, replacing the manager's single gym,
   the coach's gym field and coach rows in the membership list (carried over);
   access worked out from it; coach links become typed support-team links with
   their source; a gym assigns only its own staff.
3. **Squads**: squads, squad fighters and squad staff; access through the
   squad; sessions record their gym and squad; a Squads page for owners and
   head coaches; squads on the fighter's Team page and the coach's "My
   fighters"; squad views on the gym dashboard.
4. **Joining and camps**: join code / QR and approval, the trial-to-active
   path, emergency contact, the gym's rules accepted, camps tied to bouts,
   attendance by squad.

Not planned: payments and billing; scheduling, ring reservations, device
checkout and credential tracking until the study needs them.

## Consequences

- `tests/integration/test_gym_workflow.py` (step 1).
- Every later step gets its own record as it is built.

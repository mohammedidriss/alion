# 043. Rest Mode at each bell, and a debrief with the coach's read first

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The review board's corner P0: a 60-second screen with at most three cards,
readable at a glance under ring lights, with evidence one tap away and no dead
ends; and for appropriate reliance (H1–H3), feedback on every card and a debrief
that asks for the coach's own judgement before showing the system's.

## Decision

- **Rest Mode** (`components/RestMode.tsx`): on a multi-camera training session
  with a round plan, each bell but the last pauses every camera and sensor ("Round
  N over. Rest.") and opens the corner screen; a countdown runs the rest, says "Ten
  seconds", and at 0 resumes the same clip. A switch turns it off (remembered per
  browser); then a manual pause after a round offers "Rest cards".
  - Three cards in fixed places, headline ≥ 24 px, number ≥ 48 px, buttons ≥ 56 px
    tall; light and high-contrast by default, dark on request; shape and label with
    every colour.
  - The template cards show at once; the model's verified phrasing replaces a card
    when it arrives (ADR-041). Recovery refreshes every 10 s as the rest runs.
  - "Evidence ▾" raises a drawer over the lower half with the cited facts, their
    streams, quality and evidence level; "✓" and "✕" log noted/dismissed.
  - The footer says what the cards are: punches thrown, training information, not
    medical advice; the coach decides.
- **Card feedback** (`card_feedback`; `POST/GET /sessions/{id}/rest_cards/feedback`):
  noted, dismissed, or the coach's own read, with the facts' hash.
- **Debrief** (`components/RestDebrief.tsx`, completed sessions): for each rest, the
  coach writes their read of the round first, then reveals the cards and marks each
  useful or not; any rest can be reopened as the corner saw it.

## Consequences

- Sessions with a round plan now pause at the bell unless the switch is off — the
  plan's rests become real pauses, which is what `rounds_export` already assumed.
- The physician view the board described is not built (its regulatory status is
  open); the cards stay training information for the coach.

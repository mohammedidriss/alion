# 033. A Privacy & consent page, and requests a person acts on

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

An external review found no clear privacy and consent experience: the protections
the proposal promises (local-only data, consent, withdrawal, controlled access)
were built (ADR-014, -016, -017, -021) but not visible or actionable in the app.

## Decision

- **`/privacy`, for everyone signed in** ("Privacy & consent" in the menu):
  - where the data lives — this computer, not a cloud; AI advice written on this
    computer or another on the same network; research datasets by code, exports
    face-blurred; health-note reads logged;
  - what Alion keeps about them, with counts — for a fighter: sessions, sessions
    with heart rate and with wrist data, health notes, coach notes, AI advice;
  - who can see it — the role table (ADR-017) in plain words, and for a fighter
    who that is right now: their current coaches, their gyms and managers;
  - what they agreed to — the terms version and date, and each research dataset
    they're in by code with its consent;
  - requests: a copy of their data, leaving the research datasets, deleting their
    account and data — one open at a time per kind, with the replies.
- **Requests are handled by a person** (`data_request`, migration `f7b9d1e3a5c7`;
  `/v2/privacy/*`): admins and researchers see them on "Data requests"
  (`/privacy/requests`) and close each as done or declined with a reply the
  person reads. Nothing is deleted or exported automatically: deleting or
  withdrawing touches coaches' records and research data, and a copy is checked
  before it leaves this computer. Withdrawal itself is ADR-014's (by code).

## Consequences

- `tests/integration/test_api_privacy.py`.
- A request that's closed can be made again.

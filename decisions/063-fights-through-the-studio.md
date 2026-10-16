# 063. Fights go through the camera studio

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6

## Context

The owner asked (15 Oct 2026) for one button to start every camera, without
scanning QR codes each time. Training sessions and dataset takes already have
this: a phone scans the coach's studio QR once, then follows whichever capture
is open, and Start starts every phone together (the camera studio, ADR-010 and
ADR-017). Fights didn't. A fight is two sessions, one per corner. Every camera
tracks one person, so each camera belongs to a corner, and the fight page handed
out each corner's own QR for every fight.

Another assessment (Codex) proposed one shared recording analysed for both
fighters. That needs pose tracking of two people that keeps red and blue apart,
which isn't built, and one-button start doesn't need it.

## Decision

- **A fight is a studio capture**: opening the fight page points the coach's
  studio at it (`PUT /v2/studio/active`, kind `bout`). The coach must be able to
  record at least one of its corners.
- **Each linked phone has a corner**: red, blue or none, picked on the fight page
  and kept with the studio (`PUT /v2/studio/phones/{phone}/corner`, on disk). It
  is remembered for every fight after, and survives an API restart.
- **A phone joins its corner on its own**: with a fight open, a linked phone's poll
  returns its corner's session and join token. The phone then joins exactly as if
  it had scanned that corner's QR. A phone waits, and its page says why, when:
  - it has no corner;
  - the fight has no session in that corner;
  - the coach may not record that corner (ADR-017).

  The corner doesn't matter outside fights: the phone joins a training session
  or a take as before.
- **The fight page** shows the studio QR (scanned once, ever), each linked phone
  with a Red / Blue / Off picker, and how many cameras each corner has ready.
  Start fight already starts both corners together. Each corner's own QR stays as
  a fallback, under "Phone not linked?".

## Consequences

- `test_fight_studio.py`:
  - each phone joins its corner's session and registers with its token;
  - corners carry over to the next fight and through a restart;
  - "Off" waits in a fight but still joins a session;
  - a missing corner is explained;
  - a coach with neither fighter is refused.
- **Phones lose their link when the laptop's address changes.** A phone keeps its
  studio link in that page's own storage, so a QR made for 192.168.68.107 and a
  page at 192.168.68.111 are strangers. The address has changed at least twice
  (the HTTPS certificate covers .107 and .113; it is .111 now), and each change
  means scanning again and a certificate warning. A fixed address for the laptop
  (a reservation on the router), or the phones using the laptop's `.local` name
  (in the certificate), would end that. That isn't decided here.
- Analysing both fighters from the same cameras stays future work. It would need
  two-person pose with consistent identities.

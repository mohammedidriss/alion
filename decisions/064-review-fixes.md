# 064. What the full review of ADR-058 to ADR-063 fixed

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6
- **Amends**: ADR-058, ADR-059, ADR-060, ADR-061, ADR-062, ADR-063 (and the system-administrator guard, commit 9ddeaa2)

## Context

The owner asked (15 Oct 2026) for every new change to be tested and reviewed in
full. Four reviews ran in parallel: the model comparisons, the punch counting,
accounts and the camera studio, and the rename. They read the code paths end
to end and reproduced what they reported. Separately, every read endpoint was
called on a copy of the real database (148 of them, no errors), and each feature
was run end to end on real data: a real comparison on both of the owner's
models, a fight with two real fighters, and the researcher account.

## Decision — fixed

**Model comparisons (ADR-058)**
- A database error mid-run left the comparison "running" and blocked every later
  one until a restart. The run now always frees its slot. The slot is taken in
  the same step as the one-at-a-time check, so two can't start together. A stale
  "running" row is re-read before it's marked as stopped.
- One event loop serves a whole run. It used to be one per trial, which left
  model clients to be closed on a dead loop ("Event loop is closed").
- The summary now:
  - counts a run that never answered as 0 cards in consistency, and as the
    slowest;
  - leaves rounds with no facts out of every count;
  - covers up to 24 rounds, not 12.
- A blind rating is kept once the names are shown; it can't be overwritten.
  Ratings are one per rater and trial.
- Error text before the reveal no longer names the setup, the model or its
  address.
- Waking a model gives up after 180 s.
- The dashboard refreshes the history whenever a comparison is opened, and
  drops replies for one no longer on screen. Only researchers see the panel.
  "Your rating" now says what it shows: everyone's mean.

**Punch counting (ADR-059, ADR-060)**
- **Live counting only what's new**: the live wrist count recounted the whole
  recording on every poll, under one lock for every capture. A 30-minute session
  took about 1.5 s per poll and kept growing. Now a punch more than 4 s behind
  the newest sample is counted once and kept, each poll counts only the tail
  with 4 s of context, and older samples are let go. Each capture has its own
  lock.
  - On a real 19,000-sample session the count is identical to counting it all
    at once, on both the fixed settings and the trained counter.
  - The slowest poll takes 50 ms, whatever the length.
- A capture that starts over (its clock goes back), or a new Start, starts its
  count over. The stream is dropped when the capture completes.
- A take whose sensors were marked as worn swapped is counted on the real
  wrists, sample by sample. Before, only the totals were swapped.
- **A counter is used only if it beat what it replaces**: the camera counter is
  the newest by its report's training date (not the file's), among those whose
  held-out F1 beat the detector's. The wrist counter is the newest version
  whose held-out F1 beat the fixed settings.
- **A counter that fails to load** is remembered as failed and isn't reported as
  in use. So a cross-check made meanwhile isn't saved under its name, and it
  isn't reloaded and logged on every poll.
- Models and reports are saved beside their name and moved into place in one
  step (`model_files`).
- A candidate punch next to a dropout in the sensor's stream (no usable window)
  is judged as the fixed settings would, by its height, rather than dropped.
- The wrist counter learns from candidates found in each wrist's whole stream,
  so a block's first and last punches see their real neighbours.
- The detector places each punch on its tallest sample with a slice, not a scan
  of the whole stream.
- The camera panel shows the wrist count as the headline only while both
  wrists are connected; otherwise it shows the cameras' estimate. Its polls
  don't stack up.
- A camera's view check reports only its last 2.5 s and clears when the camera
  stops sending. The laptop's own tile shows its badge too.

**Accounts and the camera studio (ADR-062, ADR-063, 9ddeaa2)**
- **Research access couldn't be claimed by an address** (before these ADRs):
  anyone could sign up with a listed email that had no account, or switch to
  one. A plain administrator could also take one in another letter case.
  - A listed address can't be signed up for or switched to.
  - Only a researcher or the system administrator can give an account a listed
    address or the researcher role.
  - Addresses are compared in lower case.
  - A researcher-role account can't move to an unlisted address.
- **A researcher's account** can't have its password reset, its email taken, or
  be disabled by another administrator. Only a researcher, the system
  administrator or the account itself can do that.
- **The system administrator can't be moved**: an account older than it can't
  be made an admin. Promoting one would have made it the earliest admin, and
  so the protected one.
- **A role change brings its own profile** (before these ADRs): a fighter made
  a coach (or a referee) gets a new profile of that kind, as at sign-up. The
  old profile stays with what it recorded. Before, the account kept pointing
  at the fighter profile.
- The studio's saved state is written one writer at a time and moved into
  place in one step. A crossing write could lose phone corners, or the unlink
  that voids old links.
- A phone's poll checks again that the studio's owner is active and may still
  record what's open: a session, a take or a fight. A fight with no corners
  yet is open only to those who set fights up. A corner can be set only for a
  phone the studio has seen.

**Days (found applying this, just after midnight)**
- Days here are the local ones (`date.today()`), but two places took the UTC day.
  Between midnight and 3 a.m. at UTC+3 they disagreed (both before these ADRs):
  - removing an account ended its coach links on the UTC day, so for three hours
    a night they ended at once, not at the end of the day;
  - a fight camp ended on its bout's UTC day, so a camp for a bout after midnight
    local looked over the evening before.

  Both now take the local day.

**The rename (ADR-061)**
- The events CSV is now named `ringsideiq-….csv` by the API too. Its download
  links never worked: they were plain links, with no login, to an endpoint that
  needs one. Both now fetch it with the login.
- The recording windows ("RingsideIQ — live"), the start and stop scripts, and
  the training scripts' banners now say RingsideIQ.
- `terms.py` notes why a name-only change kept `draft-4`.
- The heartbeat in the mark no longer touches the ropes, and Android's round
  icon has a smooth edge (the icons are regenerated).

## Consequences

- New tests:
  - **Counting:** a 10-minute stream counted piece by piece equals counting it
    at once, keeping only seconds of it; a restart starts the count over; a
    camera or wrist counter worse than what it replaces is never used; an
    unreadable wrist model isn't named as in use.
  - **Accounts** (`test_account_security.py`): a listed address can't be
    claimed; only a researcher changes a researcher's account; an older account
    can't be made an admin; a fighter made a coach gets a coach profile.
  - **Studio:** a corner only for a known phone.
  - **Comparisons:** a missed run counts against consistency and as the
    slowest; a blind rating is kept; a failed run frees its slot.
- The test researcher is created and then listed, as a researcher's account now
  is.
- **Not changed, noted:**
  - Each comparison trial still recomputes its round's facts, which is slow
    with many repeats.
  - The keep threshold is chosen on the same held-out predictions it's scored on,
    so the reported F1 is a little optimistic.
  - The cross-check reads a swapped take's raw hands; its own left/right verdict
    depends on that.
  - A researcher's gym-staff roles outlive their place on the list.
  - Phone ids are chosen by the phones.
  - The logo is drawn in five places.
  - `PROJECT_OVERVIEW.docx` is the old Alion export.
  - At 16 px the heartbeat is a few pixels.

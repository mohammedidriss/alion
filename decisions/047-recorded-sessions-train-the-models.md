# 047. Recorded training sessions train the models

- **Status**: Accepted
- **Date**: 2026-10-14
- **Phase**: 6

## Context

The models learnt only from the research datasets' takes. Training sessions
recorded in the app — wrist sensors and cameras together, cross-checked — carry
the same kind of labels: the wrist sensors felt each punch, and the cross-check
measured each camera's clock against the wrists. The owner decided (14 Oct 2026)
that every fighter's recorded sessions train the models, with no opt-in and
nothing about it shown to fighters (ADR-046); terms draft-3 disclose it.

## Decision

`api.services.session_corpus` reads the recorded sessions from disk:

- **The camera punch counter** (`training.run`) adds every cross-checked session
  with wrist punches and a camera whose clock was matched to the wrists: one
  stretch per camera, from two seconds before the wrists' first punch to two
  seconds after their last, the wrist punches moved onto that camera's clock
  (offset, then drift), and cut where either wrist wasn't streaming (from the
  cross-check, which now keeps `wrist_gaps`, or from the samples for an older
  result) — a punch there has no label, so it mustn't be taught as "no punch".
  Pieces under five seconds are left out. Only punches the wrists felt are
  labels (`peak_g` set), never ones the cameras alone counted, so the counter
  is not taught its own guesses.
- **The punch-type models** (`camera_type_model`, `wrist_type_model`) add every
  session someone labelled with punch types (`data/labels/{session}.json`): the
  cameras' views with each camera's clock from the cross-check (as recorded when
  it wasn't matched), the wrists' samples from the database.
- **Sessions are trained on, never scored.** The counter's test stretches stay
  the dataset's, so its reports stay comparable; in cross-validation each session
  is one group, so no fold fits on a session and scores on it. The type models'
  leave-one-person-out score fits without sessions: whose a session is isn't a
  dataset participant code, and the same person could otherwise sit on both sides.
- Reports count the sessions (`data.sessions`, `data.session_punches`), shown on
  the researcher's model cards. The cross-check result now keeps each camera's
  `drift_ref_ms`, so a drifting camera's clock can be undone here.

On the live data: 4 sessions (8 camera views, 526 wrist punches) join the counter's
training; 1 labelled session (4 punches, no camera) joins the wrist type model.

## Consequences

- `tests/integration/test_session_training.py`; the integration tests see no
  recorded sessions unless they lay some down (`recorded` fixture).
- A session the cross-check never ran on adds nothing; the cross-check runs on
  its own when a camera's pose lands.
- A punch the wrists missed while streaming is still taught as "no punch" — the
  same label noise as the datasets' takes.
- Models are retrained only when a researcher starts a training run; nothing
  retrains on its own.

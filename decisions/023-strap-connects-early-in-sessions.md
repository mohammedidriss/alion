# 023. Training sessions connect the paired strap early, like dataset takes

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

On a dataset take (ADR-013) the paired Polar H10 connects as soon as the page
opens: it streams live but stores beats only from the cameras' t = 0, re-timed by
arrival onto the take's timeline. Training sessions kept the older path: beats
went straight into `hrsamplerow` as they came, timed by the strap's own clock from
the moment it connected. Connecting early would have stored beats from before
Start and shifted the session's heart rate off the video, so the session page
connected only at Start, and the coach had to press **♥ Connect strap** to see the
heart rate beforehand. Pressing it then made Start report that the strap "didn't
start" (already running), and the beats before Start were stored anyway.

## Decision

- **Armed start for sessions.** `POST /v2/sessions/{id}/hrv/ble/start` takes
  `arm`. Armed, or once the cameras have started, the stream runs with
  `wall_clock=True` and stores each beat only if the cameras filmed it, at its
  place on the clip's timeline (`capture_coord.timeline_at_ms`): nothing before
  t = 0, nothing during a pause (paused time is cut out, as MediaRecorder cuts it
  from the clip, and as the wrist sensors already do), nothing after Stop. Beats
  buffered when Stop is pressed still land.
- **The coordinator keeps the pauses** of the current recording (saved with its
  state, so they survive an API restart).
- **Idempotent.** Starting an already-running strap returns its status instead of
  409, so Start after an early connect is fine.
- The camera panel and **♥ Connect strap** start the strap armed, for sessions as
  for takes. A session recorded with no cameras keeps the strap's own clock.

## Consequences

- A training session's heart rate is now on the video's timeline (to about a
  second), like its wrist data; earlier sessions keep the strap-clock timing.
- `tests/integration/test_api_hrv.py` (armed storage, idempotent start, no-camera
  session), `tests/integration/test_api_capture_coord.py` (pauses and Stop on the
  timeline).

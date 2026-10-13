# 022. Live punch breakdown on every camera — by hand and type

- **Status**: Accepted
- **Date**: 2026-10-13
- **Phase**: 6

## Context

While recording, each camera showed one number: punches so far. The coach wants
to see what was thrown as it happens — jabs, crosses, hooks and uppercuts, lead
and rear — and how many came from each hand, on every camera screen of a
training session, a dataset take or a bout.

## Decision

- **Counted by hand on the camera.** Each camera names every punch it detects with
  the existing live rule (`classifyPunchType`: the wrist's direction over the last
  few frames — the same one the webcam capture already used) and keeps a tally per
  hand: straight, hook, uppercut and total (`lib/punchTally.ts`). Counting by hand
  rather than lead/rear means a camera counts correctly before it knows the stance.
- **Sent with the heartbeat.** The tally rides on the camera's heartbeat
  (`PunchTally` in `routes/capture_coord.py`) and comes back on the device list, so
  the coach's panel and the bout view show it per camera. As with the count, a
  fighter's breakdown is the one from the camera that saw the most punches.
- **Named by the stance.** The server looks up the fighter's stance once per
  capture (a take uses its own, from `take.json`) and returns it with the heartbeat
  and the device list. Screens then call the lead hand's straight the jab and the
  rear hand's the cross, and hooks and uppercuts lead or rear. With no fixed stance
  (switch, or unknown) they say left and right only.
- **Dots** (`PunchDots`): a coloured circle per type with its count — blue for
  straights, amber for hooks, pink for uppercuts — in a column per hand with the
  hand's total; a small two-row version sits on each camera tile. A punch the
  camera couldn't name counts toward its hand as "Not sure".
- The stance goes to anyone holding the capture's join token; it says nothing
  about who the fighter is and is visible on the video anyway.

## Alternatives considered

- **Run the trained type model (ADR-020) live.** It needs the wrist sensors and a
  full window after each punch; the live dots are an estimate and the trained
  model names the punches again after the session.
- **Tally lead/rear on the camera.** Wrong until the stance arrives, and wrong for
  a switch hitter; by hand is always right and is named at display time.

## Consequences

- `tests/integration/test_api_capture_coord.py` (breakdown, stance, switch,
  bad token), `tests/integration/test_api_datasets.py` (a take's own stance).
- A camera page opened before this change sends no breakdown; its tile shows the
  count only until it is reloaded.

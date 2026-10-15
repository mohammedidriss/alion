# 059. The wrists count; the cameras estimate, with the trained counter after

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6

## Context

On the "Single round" dataset (15 Oct 2026: jab, cross, lead hook and rear hook
takes) the owner saw the camera counts run well ahead of the punches thrown,
with the still hand counted when it shook. The takes showed why:

- The wrist sensors' labels were right: every punch on its hand, none on the
  other.
- The live camera count is the hand-written detector (`lib/punchDetector.ts`)
  on one camera's pose, and so is the cross-check's camera side after a
  recording. It counted 2–4× the punches, most of the extra on the hand that
  didn't punch: a guard hand's small shake, or a wrist the camera lost and
  found again, looks like a punch to it.
- Some cameras saw both wrists almost none of the time, and the slowest
  (≈ 22–24 frames a second) counted worst.
- The trained counter (v1, RQ2, 13 Oct) on the same takes, which it never
  trained on: 79% of what it counted were punches, and it found 85% of them. It
  put 32 punches on the hand that didn't punch; the detector put 543 there.

The owner chose (15 Oct 2026) four changes.

## Decision

- **The wrists give the live count** (`services.wrist_live`; `wrist_punches` on
  the session and take live readings): while recording, each wrist's own
  punches are counted from its samples as they arrive, by the same detector the
  session uses (`analyze.imu_punches`). It reads only what's new: the database
  rows after the last one seen, or a take's `imu.csv` after the last whole line.
  The camera panel's headline is that count, L and R, whenever the wrists are on;
  the live reader shows each wrist's count beside its trace.
- **The cameras estimate**: without the wrists, the headline is the highest
  camera's count, marked "camera estimate"; every camera's own count shows as
  "~N est.", on the panel's grid and on the camera's own page.
- **The trained counter counts after a recording** (`services.punch_counter`):
  the cross-check's camera events come from the newest trained counter
  (`data/ml/punch_counter/*/v*.joblib`, the newest file with its report), with
  each punch's wrist speed from the 3D pose. The hand-written detector stays the
  fallback: with no trained counter, under 30 frames, or if the model fails. The
  cross-check's version goes to 5 and its signature names the counter, so a
  session's check runs again the next time it's opened, and again after each
  new counter. `GET /v2/punch-counter` says which is in use, on
  the AI models page.
- **Training learns from every exported dataset** (`include_others`, on by
  default; the checkbox on the training card): the other datasets' exported
  takes, train and test alike, join the training stretches. The dataset being
  trained keeps its own test takes as the score, so the result still compares
  like with like. The report lists each other dataset with its punches.
- **Each camera checks its view before Start**: while ready, a camera runs pose
  without counting and reports, over the last 2.5 s, the share of frames it saw
  each wrist and both at once (visibility ≥ 0.5), and its pose frame rate. Each
  tile shows it ("both wrists 85% · 30 fps"). A camera under 70% or 25 frames a
  second gets a warning before Start, with where to put it: about 45° in front
  of the fighter, at chest height, 2.5–3 m away, the whole body and both gloves
  in frame, 60 fps where the phone offers it.

## Consequences

- `test_counting.py`: the live wrist counts grow as samples arrive, from the
  database and from a take's CSV with a half-written line; a camera's view check
  reaches the device list; training takes in another dataset's takes, and the
  newest counter is the one used, with its punches' speeds.
- After this, "Single round" has to be exported before training can include it;
  training again then makes a counter that has seen these takes, and it becomes
  the one in use.
- The detector's live estimate still over-counts. It is now labelled as an
  estimate and isn't the count.

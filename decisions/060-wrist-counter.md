# 060. A trained counter counts the wrists' punches

- **Status**: Accepted
- **Date**: 2026-10-15
- **Phase**: 6
- **Amends**: ADR-059 (what the live wrist count counts with)

## Context

ADR-059 made the wrist sensors the live count, with the detector the sessions
already used (`analyze.imu_punches`, fixed settings: 1.5 g, 350 ms). Single
round's export then showed the rear-hook take with 29 labels and a live count of
18. The labels are found with each punch type's own settings (`PROFILES`): the
labeller knows a block's type, and a round doesn't. On every labelled block of
every take (RQ2 and Single round), the fixed settings counted:

- jabs and crosses exactly;
- hooks short: 390 of 405 overall, and 18 of 29 rear hooks in Single round,
  because a hook's wrist burst is gentler;
- uppercuts half again too many, 438 for 282, because the return to guard about
  430 ms later is counted as a second punch;
- 18 punches in the no-punch blocks.

None of twelve other fixed settings did better on every kind of block: a lower
threshold catches the hooks and adds more uppercuts and shakes. The owner chose
(15 Oct 2026) to fix the count.

## Decision

- **Candidates, then a classifier** (`analyze.wrist_counter`): every burst a
  sensitive setting finds (0.8 g, 200 ms apart) is a candidate; a trained
  classifier keeps or drops each. It sees the burst's shape (the punch-type model's
  0.6 s window of acceleration and rotation) and its context: its height, how far
  away and how tall the bursts before and after it on the same wrist are, and how
  much the other wrist moved. Of two kept punches closer than 300 ms on one wrist,
  the likelier stays.
- **What it learns from** (`services.wrist_counter`): every dataset take's
  labelled protocol blocks, read-only. These are:
  - the single-punch blocks: the labels on the punching wrist, nothing on the
    other;
  - the no-punch block: nothing on either wrist;
  - combo blocks where every combo came out whole.

  Free shadowboxing sits out, because its labels come from the fixed settings.
  Takes whose sensors were worn swapped are read the right way round.
- **Scored before use**: 5-fold, grouped by take, so a take is never both trained
  on and scored. It is scored next to the fixed settings, per kind of block, and
  the keep threshold is chosen there. Each version is saved with its report
  (`data/ml/wrist_counter/v{n}`). On the takes so far (28 takes, 1,518 labelled
  punches, one participant), held out:

  | Block | Labelled | Fixed settings (found, F1) | Counter (found, F1) |
  |---|---|---|---|
  | Jabs | 211 | 211, 1.00 | 207, 0.99 |
  | Crosses | 246 | 246, 1.00 | 246, 1.00 |
  | Hooks | 405 | 390, 0.78 | 407, 0.88 |
  | Uppercuts | 282 | 438, 0.76 | 303, 0.92 |
  | Combos | 374 | 387, 0.96 | 376, 0.98 |
  | No-punch blocks | 0 | 18 false | 3 false |
  | **All** | | **F1 0.874** | **F1 0.944** |

- **The newest version counts every wrist punch**: live (`wrist_live`), in the
  cross-check, and in a session's numbers and the recordings list
  (`sensor_summary`). With no version trained, or if one fails to load or run,
  the fixed settings count, as before. The cross-check's version goes to 6 and its
  signature names the wrist counter, so a session counts again with each new one.
- **Trained from the AI models page** ("Punch counter — wrist sensors",
  researchers only: `POST /v2/wrist-counter/train`, `GET /v2/wrist-counter`), in
  about a minute.
- The live take count now uses the right wrists when the take's sensors were
  marked as worn swapped.

## Consequences

- `test_wrist_counter.py`: on synthetic takes, the fixed settings miss gentle hooks
  and count every uppercut twice; the counter, held out, counts them right and drops
  the shakes. Once trained, the newest version counts live, from a take's CSV, and
  in a session's numbers; a broken model file falls back to the fixed settings.
  Researchers only. Integration tests count with the fixed settings unless a test
  trains a counter, never with one in the checkout's `data/ml`.
- **Free rounds aren't scored.** No round has hand-counted punches. On the two
  biggest recorded sessions the counter counts fewer than the fixed settings
  (78/78 for 95/98; 109/105 for 119/115). Most of the ones it drops come
  350–500 ms after the previous punch on that wrist, at 1.6–3 g. The cameras'
  3D pose measures how far the arm extends into each one:
  - first session: a median 4–5 cm, none over 15 cm, against 9–12 cm for the
    punches it keeps — returns to guard, by the look of it;
  - second session: 12–14 cm against 15–23 cm, and a quarter of them extend
    over 15 cm, like punches.

  A round counted by hand would settle it.
- The camera counter learns from the recorded sessions' wrist punches (ADR-047).
  Once a wrist counter is in use, each session's cross-check runs again when it is
  opened. Training the camera counter after that gives it the new counts.
- Uppercuts are still counted about 7% high; hooks are the weakest kind of block
  (F1 0.88).
- One participant: the counter knows how this fighter punches, not how others do.

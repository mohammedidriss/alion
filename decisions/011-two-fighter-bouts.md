# 011. Two-fighter bouts — identity, segregation, and fusion

- **Status**: Proposed
- **Date**: 2026-09-20
- **Phase**: 5 (two-fighter bouts)

## Context

Everything the platform records today is **single-fighter**. A `Session` carries
one `fighter_id`, and every stream — punch events, IMU samples, HR samples, pose
— hangs off `session_id`. That is exactly right for a **training** session: one
athlete, one set of sensors, one clean container.

We now want to support an **actual fight**: two fighters in the ring at once, each
needing their own punch count, IMU, and HRV. This raises the questions the coach
asked directly:

- How do we **segregate** the two fighters' data?
- How do we **differentiate** them (which stream belongs to whom)?
- Do we put **two sections in one session**, or **separate the sessions**?
- What's the "home" fighter — how do we label sides?

Two hard realities shape the answer:

- **Vision cannot reliably tell the fighters apart on its own.** The Tasks
  `PoseLandmarker` we use *does* support multiple skeletons (`numPoses > 1`; it's
  set to `1` today in `CameraNode.tsx`), so detecting two bodies is not the
  blocker. But MediaPipe returns the poses as an **unordered list with no stable
  identity** across frames, and in a **clinch the two bodies merge into one
  skeleton or one drops out**. Attributing a punch to the wrong fighter happens
  precisely during infighting — the moments that matter most. This is the same
  single-camera ceiling ADR-009 ran into for *count*, now compounded by *identity*.
- **The wearables already carry identity — physically.** An IMU strap is on **one
  fighter's** wrist; a Polar H10 is on **one fighter's** chest. Their signal is
  unambiguously that fighter's, and it survives clinches and occlusion. A camera,
  by contrast, sees the **whole ring** — there is no such thing as "fighter A's
  camera." So the wearables are *sources* of identity; the cameras are *consumers*
  of it.

Constraints:

- **Minimal schema churn.** Adding a `fighter_id` to every stream table
  (`punch_event`, `hr_sample`, `imu_sample`, pose parquet) and re-grouping every
  query and aggregation would touch the whole codebase and break the single-fighter
  assumption ADR-001 modules are built around.
- **Keep training data pristine (dissertation methodology).** Controlled
  single-fighter training sessions are the primary RQ dataset. The messy
  two-fighter attribution problem must not leak into them.
- **Reuse the substrate we have**: `SessionClock`/T_0 (ADR-006), the multi-device
  coordinator and its device roster (ADR-010), the per-node registration, and the
  ring-bell sync marker. This ADR should compose them, not reinvent them.

## Decision

**One fighter = one session. A *bout* links two sessions.** We do not put two
fighters inside a session; we keep each fighter's data in its own single-fighter
session and add a **`Bout`** entity that records the two were fought together.

1. **Segregation primitive — the session.** Because every stream is already keyed
   by `session_id`, and a session is one fighter, per-session *is* per-fighter.
   Segregation comes for free from the existing model; no `fighter_id` columns are
   added to any stream table. A **training** session is simply a session with no
   bout. A **fight** is two sessions, one per fighter, both pointing at a bout.

2. **The `Bout` entity.** Holds what is genuinely shared by both fighters: a label,
   date, the **round configuration**, and the **bell/round timeline**. It
   references the two participant sessions and assigns each a **corner** —
   `red` / `blue` (the boxing convention, in place of "home/away"). `Session` gains
   two additive fields (per ADR-005): `bout_id` (null ⇒ training) and `corner`.

3. **Device → corner → session assignment.** When a device is paired it is assigned
   to a corner, which routes its data to that fighter's session. The IMU strap and
   the Polar H10 are **physically owned** by one fighter, so this assignment is
   exact and their streams can never mix. This is the mechanism that "differentiates
   the two fighters."

4. **CV identity is *anchored to the IMU*, not sourced from vision.** A shared
   camera runs `numPoses: 2` + a lightweight frame-to-frame tracker to keep two
   skeletons apart, but the **corner label on each detected punch is decided by the
   IMU**: the IMU says "red threw at t≈3.2 s," so the CV event nearest that instant
   is attributed to red. Vision supplies *technique/type/position*; the IMU supplies
   *who and when*. When no IMU is present (CV-only fallback), the tracker's corner
   assignment is used but flagged **low-confidence**, and overlapping-torso windows
   are marked **ambiguous** rather than mis-attributed.

5. **One bell, two aligned timelines.** The bout's single bell anchors **both**
   sessions' `SessionClock` T_0 (ADR-006). The two fighter timelines are therefore
   aligned by construction — no cross-session clip-syncing — and per-round,
   head-to-head comparison is a straight join on offset-from-T_0.

6. **Fusion stays per fighter.** The event-level fusion from the multi-camera work
   runs **within each session** (keyed by corner), producing one fused punch stream
   per fighter. The bout view is a read-side join of the two.

What changes: a `Bout` table; two additive `Session` fields; coordinator support
for corner assignment; `numPoses: 2` + tracker in the camera node; the IMU-anchored
attribution step; a bout view. What does **not** change: every stream table, every
existing single-fighter query, and the entire training-session path.

## Schema sketch

The concrete delta (a sketch to make the migration reviewable, not the final
DDL). Additive per ADR-005; **no stream table changes**.

```
Bout (new)
  id                UUID  pk
  label             str?             # "Smith v Jones — sparring wk3"
  scheduled_at      datetime
  venue             str?
  round_count       int              # shared round config lives here for a bout
  round_duration_s  int
  rest_duration_s   int
  red_session_id    UUID  fk -> session   # exactly one red …
  blue_session_id   UUID  fk -> session   # … and one blue
  winner_corner     enum(red|blue|draw)?  # result, filled post-bout
  result_method     str?                  # KO / TKO / decision / …
  created_at        datetime

Session (additive — two new nullable fields)
  bout_id           UUID? fk -> bout  # null  => training session (today's path)
  corner            enum(red|blue)?   # this session's side of the bout

BellEvent (new) — the shared round timeline, as offsets from the bout T_0
  id                UUID  pk
  bout_id           UUID  fk -> bout
  round_index       int
  kind              enum(round_start|round_end|bell)
  t_ms              float            # offset from the shared SessionClock T_0
```

Invariants:

- A bout has **exactly two** participant sessions — one `red`, one `blue` — and
  both anchor their `SessionClock` T_0 to the bout's bell, so their timelines are
  directly comparable (ADR-006).
- For a bout, the **round config is authoritative on `Bout`**; the two sessions
  defer to it (single source). A **training** session keeps its own round config
  on `Session`, unchanged.
- `bout_id IS NULL` ⇔ training ⇔ every existing single-fighter query, aggregation,
  and view is untouched. The bout path is purely additive.

## Alternatives considered

- **Multi-participant session** (one session, two fighters; add `fighter_id` to
  every stream row) — rejected. Massive, cross-cutting schema churn; every query
  and aggregation must re-group by fighter; it breaks the single-fighter invariant
  the modules rely on; and it risks contaminating clean training data with bout
  complexity. The linked-sessions model gets the same expressive power with two
  additive fields.

- **Vision as the source of identity** (`numPoses: 2` + tracker is the truth, no
  IMU anchor) — rejected. Identity swaps and skeleton merges in the clinch are a
  known-hard CV problem; making attribution depend on it is not defensible for a
  dissertation. Vision is kept as a *consumer* of identity and a cross-check, never
  the arbiter.

- **Per-fighter dedicated cameras as the segregation** — rejected. A camera sees
  the whole ring; a "red camera" still captures blue. Dedicated angles are useful
  for *coverage*, but they cannot physically own a fighter, so attribution is still
  required. Physical ownership lives with the wearables, not the cameras.

## Consequences

- **Positive**
  - Tiny schema delta (`Bout` + two additive `Session` fields); all existing
    per-session machinery works unchanged, once per fighter.
  - IMU/HRV segregation is exact and survives clinches — no vision identity needed
    for the streams that carry it.
  - Training data stays pristine and separate from bouts (methodologically clean).
  - Bell-anchored T_0 aligns the two sessions for free; head-to-head is a join.
  - Reuses ADR-006 clock, ADR-010 coordinator, and ADR-009 detector as-is.

- **Negative / risks**
  - CV attribution is only as good as the IMU anchor; the CV-only fallback will be
    low-confidence and must degrade to *ambiguous* rather than guess. This is an
    honest limit, surfaced in the data, not hidden.
  - Shared metadata (round config, bell) is denormalized relative to two sessions;
    it must live on the `Bout` to stay single-source.
  - Two-session bouts add a join to queries and a combined view to the UI.
  - The detector now runs **per tracked identity**, so `punchDetector.ts` and
    `punch_detector_extension.py` must stay in sync per ADR-009 — now instantiated
    per corner.

- **Follow-ups**
  - Migration: `Bout` table, `bout_id` + `corner` on `Session`.
  - Coordinator: corner assignment on device registration (extends ADR-010 roster).
  - Camera node: `numPoses: 2` + frame-to-frame tracker with the ambiguous-window
    guard.
  - Attribution: IMU-timing → corner labelling of CV punch events.
  - UI: bout view — two fighter panels, shared timer/bell, per-round head-to-head.
  - Fusion: per-corner event-level fusion; bout-level read join.

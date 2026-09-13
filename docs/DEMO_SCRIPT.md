# Alion — Prototype Demo Script & Storyboard

**Purpose:** a screen-recorded walkthrough of the initial prototype — how the system
captures a boxing session, detects and classifies punches, and where it's heading.
**Length:** ~5 minutes. **Audience:** technical-but-mixed (supervisor / panel / stakeholders).
**Tone:** honest prototype — show what genuinely works, name what's next. Don't oversell.

---

## Pre-flight checklist (do this BEFORE you hit record)

- [ ] Dev server running: dashboard on `http://localhost:3000`, API on `:8000`.
      (Start with your usual `make dev` / launch config.)
- [ ] Logged in already (don't record the login).
- [ ] One fighter exists with a **stance set** (e.g. "Mohamad — ORTHODOX"). Stance drives
      jab-vs-cross labeling, so it must be set.
- [ ] Camera at **~45° to your side**, not head-on. Good, even lighting. Upper body + both
      hands in frame. (Head-on is the hardest angle for a single camera — 45° demos best.)
- [ ] Decide your punch set and **rehearse it once** (see Scene 3). Throw deliberately, not
      at full combo speed — a clean on-camera count matters more than realism here.
- [ ] Close noisy tabs/notifications. Screen-record at 1080p. Have this script on a 2nd screen.
- [ ] (Optional, only if you'll show the IMU beat) a terminal open at the repo root.

---

## Storyboard

Each scene: **[SHOW]** = what's on screen / what you click · **[SAY]** = your talking points.

### Scene 1 — The problem (≈30s) · *talking-head or title slide*
- **[SHOW]** Title: "Alion — objective, multi-modal boxing analytics." Or just talk over the dashboard home.
- **[SAY]**
  - "Coaches judge punches by eye. The wearables that exist — Hykso, StrikeTec — are closed:
    they give you a number in *their* app, not the raw data, and some are already discontinued."
  - "Alion is a research platform that captures a boxing session from **multiple sensors**,
    keeps the **raw data**, and fuses it into objective feedback — built for a dissertation, so
    every number has to be defensible."

### Scene 2 — Architecture in one breath (≈40s) · *one diagram or the /fighters page*
- **[SHOW]** A simple diagram (or just narrate). Point to the modules.
- **[SAY]**
  - "The pipeline: **camera → MediaPipe pose → punch detector → typed events → dashboard.**"
  - "It's modular by design — computer vision, an **IMU** wrist sensor, **heart-rate variability**,
    and a between-rounds **camera-based pulse** fallback all feed one shared schema, then a
    fusion layer reconciles them."
  - "Today I'll demo the **camera** path end-to-end live — that's what's working now — and show
    where the IMU plugs in next."

### Scene 3 — Live capture (the core, ≈90s) · *the money shot*
- **[SHOW]** Navigate to **`/sessions/new`** → pick your fighter from the dropdown (shows
  `Name (STANCE)`) → it creates the session and lands on the session page.
- **[SHOW]** In the **Browser Capture** panel, click **"Start capture"** → "Loading model…"
  (MediaPipe loads in the browser) → click **"Begin recording"** → a **3-2-1 "Get ready…"**
  countdown.
- **[SAY]** (while it loads) "Pose detection runs **entirely in the browser** — no video leaves
  the machine unless we save it. The skeleton you're about to see is 33 tracked body points in
  real 3D."
- **[SHOW]** Now throw your rehearsed set at ~45°, deliberately:
  **4 jabs (lead hand) · 3 crosses (rear hand) · 2 hooks · 1 uppercut = 10 punches.**
  The live **"N punches detected"** counter ticks up with each one; the skeleton overlays your body.
- **[SAY]** "Watch the counter — every punch is being detected live from the wrist motion."
- **[SHOW]** Click the red **"Stop & save"** → "Saving…" → **"✓ N punches saved."**
- **[SAY]** "On stop it uploads three things: the **punch events**, the full **pose stream** for
  offline analysis, and the **video clip** so we can verify the count against reality."

### Scene 4 — The results (≈60s) · *session page*
- **[SHOW]** The session page now shows the **punch count**, the **per-type chart** (jab / cross /
  hook / uppercut), the **timeline**, and a **Recording** section with the saved clip.
- **[SAY]**
  - "Here's the session. The count, and — this is new this week — the **punch *types*** broken
    down: jabs, crosses, hooks, uppercuts."
  - "And the recorded clip lets a coach **verify** the count against what actually happened —
    important for a study, where I can't just trust the number."
- **[SHOW]** (optional) Scrub the video next to the timeline.

### Scene 5 — How the detection works (≈45s) · *talk over the skeleton / a still*
- **[SAY]**
  - "Detection uses **three complementary 'gates'**, because punches don't all look alike to a
    camera: a **wide-excursion** gate catches hooks, an **elbow-extension** gate catches straight
    jabs and crosses thrown *toward* the camera, and an **upward-drive** gate catches uppercuts."
  - "It runs on the **3D world coordinates**, so wrist speed is in real metres per second."
  - **Honesty beat:** "A single camera can't fully see a punch thrown straight down the lens —
    depth gets compressed. On a labelled test it nailed the straight-punch count exactly; type
    labels are a first-pass heuristic. That ceiling is *exactly* why the next sensor is an IMU."

### Scene 6 — Where it's heading (≈45s) · *fighter IMU/HRV tabs, or terminal*
- **[SHOW]** Navigate to a fighter's **IMU** and **HRV** tabs (`/fighters/[id]/imu`, `/hrv`) —
  the slots are already in the UI. (Optional: show the sensor in hand on camera.)
- **[SAY]**
  - "The wrist **IMU** — a WitMotion WT901BLECL — arrived this week. I did full due diligence
    before buying: open raw data, works over Bluetooth on this machine, and it drops into the
    same schema the camera uses. That's the next integration."
  - "Beyond that: **heart-rate variability** from a chest strap for fatigue, a **camera-based
    pulse** fallback between rounds, and an **LLM 'corner' layer** that turns the fused data into
    coaching cues."
- **[SAY]** (close) "So: the camera path is live today, the data model and UI are already built
  for the rest, and the IMU is next on the bench. That's the prototype."

---

## Talking-point cheat-sheet (grab-bag, for questions)

- **Why not a phone app / existing tracker?** Closed data, not research-grade, and consumer
  trackers are consolidating/disappearing (Hykso → FightCamp). Alion keeps raw signals.
- **What's a "world landmark"?** MediaPipe gives 33 body points in real-world 3D metres
  (hip-centred), so velocities are physical, not pixel-based.
- **Why three gates?** One heuristic can't catch a hook (wide), a jab into the lens (no lateral
  motion), and an uppercut (vertical) at once. Each gate covers a blind spot of the others.
- **How accurate is it?** On the one labelled session: straight-punch count exact; total slightly
  over (a few doubles from jitter). Recall looks complete. Types are a v0.5 heuristic. The IMU is
  the accuracy source going forward — the camera gives context (position, stance, movement).
- **Architecture discipline (if asked):** hexagonal/ports-and-adapters, schema-first, every major
  choice is an ADR. Feature modules only depend on shared contracts — so adding the IMU can't
  break the camera path.

## Do / Don't on camera
- ✅ Do call it an **initial prototype**. Show the live count working — that's the wow.
- ✅ Do name the monocular limitation *before* someone else does; it sets up the IMU story.
- ❌ Don't claim per-type accuracy is validated — it isn't yet (say "first-pass").
- ❌ Don't throw blazing combos on camera — deliberate, separated punches read clean.
- If a stray count happens, own it in one line: "single camera, you'll see why the IMU matters."

## Suggested recording order (edit-friendly)
Record Scene 3 (live capture) **first** while you're warm and the lighting's set — it's the
hardest to redo. Record the narration scenes (1, 2, 5) after, over screenshots/stills. Splice.

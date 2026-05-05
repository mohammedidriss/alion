# CV improvement roadmap

Tracks the full list of CV improvements requested. Status legend:
🟢 done · 🟡 in progress · ⚪️ queued · 🔵 deferred (later phase)

> Source: ADR 003 + the 5 May 2026 review. Punched-up after the user
> reported the punch count is inaccurate and asked for a camera selector.

## Priority 1 — Detection accuracy (the "count is wrong" bucket)

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | MediaPipe **world landmarks** for metric 3D velocity | 🟡 | Foundation for accurate velocity. Replaces the body-width hack. |
| 5 | **Whole-body motion filter** (reject events when torso translates) | 🟡 | Kills false positives from walking/turning. |
| 24 | **Forward-extension check** in the punch detector | 🟡 | Require wrist to *extend away from shoulder* before a deceleration counts. |
| 2 | **Sub-frame cubic-spline interpolation** for peak velocity | ⚪️ | 30 fps undersamples fast jabs. |
| 6 | **Per-frame pose confidence** persisted in parquet | ⚪️ | Lets the dashboard flag low-quality sessions. |

## Priority 2 — Type / labels

| # | Item | Status | Notes |
|---|---|---|---|
| 4 | **Stance-aware hand labels** (lead vs rear) | 🟡 | Free win — `Fighter.stance` already in DB. |
| 3 | **Heuristic punch-type classifier** (jab/cross/hook/uppercut) | ⚪️ | Pulled from Phase 3. Same `PunchEvent` field; LSTM replaces later. |

## Priority 3 — Capture UX

| # | Item | Status | Notes |
|---|---|---|---|
| 25 | **Camera dropdown selector** | 🟡 | New ask. Enumerate available indices, default to 0, persist choice. |
| 11 | **Pause / Resume** alongside Stop | ⚪️ | |
| 22 | Camera health panel during live capture (FPS, dropped frames) | ⚪️ | |
| 9 | Punches/minute live counter | ⚪️ | |
| 10 | Round timer (3 min on / 1 min rest) | ⚪️ | Touches Phase 7 study mode. |
| 12 | Annotate session (notes + tag) | ⚪️ | `notes` column already exists. |
| 21 | Lighting / pose-quality warning | ⚪️ | Depends on #6. |
| 23 | Re-process button on completed sessions | ⚪️ | |

## Priority 4 — Session analytics on the detail page

| # | Item | Status | Notes |
|---|---|---|---|
| 7 | **Punch timeline** (events vs time) | ⚪️ | Uses existing data. |
| 8 | **Velocity distribution histogram** | ⚪️ | Uses existing data. |
| 13 | Snapshot of "hardest punch" with skeleton + velocity badge | ⚪️ | |
| 14 | Replay video with skeleton burned in | ⚪️ | |

## Priority 5 — Cross-session / fighter level

| # | Item | Status | Notes |
|---|---|---|---|
| 17 | Fighter measurements (shoulder width, height, weight, dominant hand) | ⚪️ | Feeds Tier B calibration; small. |
| 15 | Fighter detail page with longitudinal stats | ⚪️ | Pulled from Phase 6. |
| 16 | Compare two sessions side-by-side | ⚪️ | Pulled from Phase 6. |

## Priority 6 — Outputs / sharing

| # | Item | Status | Notes |
|---|---|---|---|
| 18 | CSV export of events | ⚪️ | One hour. |
| 20 | Save MJPEG preview to MP4 (skeleton burned in) | ⚪️ | |
| 19 | Per-session PDF report | 🔵 | Phase 6 deliverable. |

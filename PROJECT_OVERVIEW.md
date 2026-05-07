# Alion — Project Overview

Multi-modal AI coaching platform for combat sports. Validation artifact for a
DBA dissertation at Golden Gate University. Boxing is the validation domain.

> Not a medical device. Not a diagnostic tool. Advisory only. Local-only data
> by IRB constraint — see [ADR 002](decisions/002-encryption-deferred.md).

This document is the deep reference. For a one-page run-it-locally guide see
[README.md](README.md). For agent-facing engineering rules see
[CLAUDE.md](CLAUDE.md).

---

## Table of contents

1. [System at a glance](#1-system-at-a-glance)
2. [Architecture & module boundaries](#2-architecture--module-boundaries)
3. [Data model — every table explained](#3-data-model--every-table-explained)
4. [API — every endpoint explained](#4-api--every-endpoint-explained)
5. [Frontend — every route, tab, and component](#5-frontend--every-route-tab-and-component)
6. [Algorithms & analytics](#6-algorithms--analytics)
7. [CLI scripts](#7-cli-scripts)
8. [Cross-modality alignment (SessionClock)](#8-cross-modality-alignment-sessionclock)
9. [Migrations history](#9-migrations-history)
10. [ADRs (architecture decisions)](#10-adrs-architecture-decisions)
11. [Testing strategy](#11-testing-strategy)
12. [Operations](#12-operations)
13. [Known limitations & honest caveats](#13-known-limitations--honest-caveats)
14. [Roadmap](#14-roadmap)

---

## 1. System at a glance

Three runtimes:

| Service | Port | Stack | Purpose |
|---|---|---|---|
| FastAPI backend | 8000 | Python 3.11 + FastAPI + SQLModel + SQLite + Pydantic v2 | All business logic, capture orchestration, HRV streaming, evaluation |
| Next.js dashboard | 3000 | Next 14 (App Router) + React 18 + Tailwind | Human-facing UI; pure browser-side, talks to API over fetch |
| Capture worker | in-process | MediaPipe Pose + OpenCV + threading | Pose extraction + heuristic punch detection; runs as a daemon thread inside the API process |

Three profile types:

- **Fighter** — boxer being measured. Has sessions, HRV baselines, medical records, team (coaches + titles + sponsors), career history, photo.
- **Coach** — trainer. Has identity + contact + credentials + bio; can be assigned to fighters via `CoachAssignment`.
- **Referee** — sanctioned official. Identity + license/sanctioning body + bio.

All data is local-only: SQLite at `data/alion.db`, photos at `data/photos/`, raw videos at `data/raw/uploaded/`, pose parquet at `data/processed/`, manual labels at `data/labels/`.

---

## 2. Architecture & module boundaries

**Hexagonal/ports-and-adapters**, enforced by `import-linter`. The contract: `api` is the only composition root; feature modules don't import each other.

```
                 ┌─────────────────────────────────────┐
                 │   api  (FastAPI — composition root) │
                 └─────────────────────────────────────┘
                       ▲              ▲             ▲
        ┌──────────────┘              │             └────────────┐
        │                             │                          │
   ┌────┴────┐  ┌────────┐  ┌─────────┴────┐  ┌───────┐  ┌──────┴────┐
   │ capture │  │analyze │  │   store      │  │studies│  │   coach   │
   │ /cv     │  │        │  │  (SQLModel)  │  │(eval) │  │  /grounding│
   │ /hrv    │  │        │  │              │  │       │  │  /fusion  │
   └────┬────┘  └───┬────┘  └────┬─────────┘  └───┬───┘  └─────┬─────┘
        │           │            │                │            │
        └───────────┼────────────┼────────────────┼────────────┘
                    ▼            ▼                ▼
                 ┌────────┐  ┌────────┐
                 │contracts│  │ common │
                 │(Pydantic│  │(time,  │
                 │  events)│  │ logging│
                 └────────┘  └────────┘
```

| Package | Role | Imports allowed |
|---|---|---|
| `contracts` | Pydantic event/sample types crossing module boundaries (`PoseFrame`, `HRSample`, `PunchEvent`) | none |
| `common` | Settings, logging, `SessionClock` time utilities | `contracts` |
| `store` | SQLModel tables + repos. SQLite is the only persistence | `contracts`, `common` |
| `capture/cv` | MediaPipe wrapper, webcam/file frame sources, draw_pose overlay, capture pipeline | `contracts`, `common` |
| `capture/hrv` | RR-CSV parser + replay driver for HRV streams. Polar BLE TBD | `contracts`, `common` |
| `analyze` | Stateless pure-function analysis: HRV metrics, heuristic punch detector, punch-type classifier, velocity refiner, performance score, readiness | `contracts`, `common` |
| `studies` | Detector evaluation (precision/recall/F1, confusion matrix, label loader) | `contracts`, `common` |
| `coach` | Reserved for future LLM coaching layer. Not yet populated | `contracts`, `common` |
| `grounding` / `fusion` | Reserved for Phase 3 cross-modality fusion. Not yet populated | `contracts`, `common` |
| `api` | Routes, dependencies, services (capture_runner, hrv_runner, photos). Wires everything | all of above |

`pyproject.toml` declares the layered contract; `uv run lint-imports` enforces it. See [ADR 001](decisions/001-module-boundaries.md) and [ADR 004](decisions/004-phase-isolation-hardening.md).

---

## 3. Data model — every table explained

All tables live in [packages/store/models.py](packages/store/models.py).

### 3.1 Identity / profiles

#### `Fighter`

The athlete being measured. Wide schema; most fields nullable to allow coaches to fill in incrementally.

| Field | Type | Purpose |
|---|---|---|
| `id` | UUID | Primary key |
| `name`, `nickname`, `dob`, `nationality`, `sex` | text/date | Identity |
| `stance` | enum (orthodox/southpaw/switch) | Drives the heuristic detector's lead/rear hand classification |
| `dominant_hand` | enum (left/right) | Optional; used for asymmetry analysis later |
| `height_cm`, `reach_cm`, `weight_kg`, `shoulder_width_cm` | float | Physical anthropometry — also feeds CV velocity calibration |
| `skill_level` | enum (recreational → coach) | Skill spectrum |
| `weight_class` | text | One of `WEIGHT_CLASSES` enum (minimumweight → heavyweight) |
| `years_training`, `gym`, `trainer` | text | Career context |
| `record_wins/losses/draws/kos` | int | Pro/amateur record tally |
| `boxrec_id`, `usa_boxing_id` | text | External registry IDs |
| `notes` | text | Free-form |
| `photo_path` | text | Relative path under `data/photos/fighter/` |
| `bio` | text | Short paragraph for the Team tab header |
| `career_history` | text | Long-form career narrative |
| `created_at` | datetime | Audit |

#### `Coach`

Trainer profile.

| Field | Notes |
|---|---|
| `id`, `name`, `photo_path`, `dob`, `nationality`, `sex` | Identity |
| `email`, `phone` | Contact |
| `gym`, `specialties` | Free-text coaching context (specialties is comma-separated) |
| `coaching_level` | enum: amateur / professional / both |
| `years_experience` | int |
| `certifications` | comma-separated free text (e.g. "USA Boxing Level 2, AIBA 1-Star") |
| `license_number`, `license_expiry` | Credentials |
| `languages` | comma-separated |
| `notable_fighters` | comma-separated names of athletes coached |
| `bio`, `notes` | Free-form |

#### `Referee`

Sanctioned official.

| Field | Notes |
|---|---|
| `id`, `name`, `photo_path`, `dob`, `nationality`, `sex` | Identity |
| `email`, `phone` | Contact |
| `license_number`, `sanctioning_body` | e.g. WBC / WBA / IBF / USA Boxing |
| `certification_level` | enum: local / regional / national / international |
| `license_expiry`, `years_officiating` | Credentials |
| `languages`, `notable_bouts` | Track record |
| `bio`, `notes` | Free-form |

### 3.2 Sessions and events (CV)

#### `Session`

One capture run. Multiple sources (live webcam, uploaded video, HRV replay, polar-only).

| Field | Notes |
|---|---|
| `id`, `fighter_id`, `source`, `status` | Core |
| `started_at`, `ended_at` | Wall-clock — also serves as `SessionClock.wall_t0` |
| `video_path`, `pose_parquet_path` | Filesystem artifacts |
| `frame_count`, `duration_ms` | Capture telemetry |
| `notes`, `failure_reason` | |
| `baseline_rmssd_ms`, `baseline_sdnn_ms`, `baseline_mean_hr_bpm`, `baseline_recorded_at` | Pre-session resting HRV (5-min recording before warmup) |

`SessionStatus`: pending → capturing → processing → completed / failed.

`SessionSourceEnum`: live_webcam, uploaded_video, live_iphone (reserved), polar_h10_only, hrv_replay.

#### `PunchEventRow`

Detected punches. Flat per-event row produced by `analyze.HeuristicPunchDetector` (or future LSTM).

| Field | Notes |
|---|---|
| `t_ms` | Offset from session start |
| `hand` | left / right |
| `lead_or_rear` | Derived from fighter stance |
| `velocity_ms` | Peak wrist velocity in m/s |
| `velocity_source` | `world` (3-D world landmarks) or `image_heuristic` (image-plane fallback) |
| `punch_type` | jab / cross / hook / uppercut, nullable when classifier is unsure |
| `detected_by` | `heuristic` or `lstm_v1` |
| `confidence` | 0.0–1.0 |

#### `HRSampleRow`

One heart-beat from the HRV stream.

| Field | Notes |
|---|---|
| `t_ms` | Session-start offset |
| `rr_ms` | RR interval (this beat – previous) |
| `hr_bpm` | 60 000 / rr_ms |

### 3.3 Weight tracking

#### `WeighIn`

Time-series weigh-ins per fighter; the latest also mirrors onto `Fighter.weight_kg`.

| Field | Notes |
|---|---|
| `weight_kg` | The reading |
| `recorded_at` | Wall-clock |
| `notes` | |

### 3.4 Medical (fighters only)

Confidential per-fighter medical context. Local-only by design. Surfaced on the **Medical** tab with a critical-info red banner when severe items exist.

#### `MedicalRecord` (1:1 with Fighter)

Blood type, last clearance date + clearing physician, primary physician + phone, emergency contact (name/relation/phone), insurance provider/policy, free-form notes, `updated_at`.

#### `Allergy` (many)

Per substance: severity (mild / moderate / severe / anaphylactic), notes.

#### `Medication` (many)

Name, dose, frequency, started_on, prescribed_by, `is_active`, notes.

#### `MedicalCondition` (many)

Name, diagnosed_on, status (active / managed / recovered), notes.

### 3.5 Team / titles / sponsors

#### `FighterTitle`

Championship belts and amateur titles.

| Field | Notes |
|---|---|
| `name` | "WBC heavyweight" |
| `organization` | WBC / WBA / IBF / WBO / amateur federation |
| `weight_class` | |
| `won_on`, `lost_on` | |
| `status` | active / lost / vacated / retired |

#### `FighterSponsor`

Commercial sponsorships.

| Field | Notes |
|---|---|
| `name`, `website` | |
| `started_on`, `ended_on` (None = current) | |
| `notes` | |

#### `CoachAssignment`

Many-to-many between Fighter and Coach with role.

| Field | Notes |
|---|---|
| `coach_id` | FK to a real Coach profile (the Team tab pulls from the roster) |
| `role` | head_coach / striking / strength / conditioning / nutrition / cutman / mental / other |
| `started_on`, `ended_on` (None = current) | |
| `notes` | |

The list-endpoint denormalises `coach_name` and `coach_photo_path` so the UI doesn't need N+1 lookups.

---

## 4. API — every endpoint explained

Run: `uv run uvicorn api.main:app --reload` (port 8000).

API versioning convention: most routes are unversioned; `/v1/*` mirrors them as the frozen Phase 1 contract; `/v2/*` is reserved for HRV. See [ADR 004](decisions/004-phase-isolation-hardening.md), [ADR 005](decisions/005-additive-fields-on-v1.md).

### 4.1 Health & meta

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | Liveness probe + schema_version |
| GET | `/health/capabilities` | Whether MediaPipe/OpenCV are importable + the most likely camera index |
| GET | `/cameras` | Enumerated cameras visible to OpenCV |
| GET | `/fighters/_meta/coach-roles` | Enum of CoachRole values for UI dropdown |
| GET | `/fighters/_meta/title-statuses` | Enum of TitleStatus values |
| GET | `/fighters/options` | Stances, hands, skill levels, weight classes, sexes for dropdowns |

### 4.2 Profiles

#### Fighters — `/fighters`

| Method | Path | Notes |
|---|---|---|
| POST | `/fighters` | Create with name + stance |
| GET | `/fighters` | List all |
| GET | `/fighters/{id}` | One |
| PATCH | `/fighters/{id}` | Update any subset of 25+ fields, including bio + career_history |
| DELETE | `/fighters/{id}` | Cascades sessions + photos |
| POST | `/fighters/{id}/photo` | Multipart upload; saves under `data/photos/fighter/{id}.{ext}` |

#### Coaches — `/coaches`

POST/GET/GET-by-id/PATCH/DELETE/POST-photo. PATCH accepts the full extended schema (dob, nationality, sex, email, phone, gym, specialties, coaching_level, years_experience, certifications, license_number, license_expiry, languages, notable_fighters, bio, notes).

#### Referees — `/referees`

POST/GET/GET-by-id/PATCH/DELETE/POST-photo. PATCH accepts the referee schema (license_number, sanctioning_body, certification_level, license_expiry, years_officiating, languages, notable_bouts, bio, notes).

### 4.3 Weigh-ins — `/fighters/{id}/weigh-ins`

GET (list, ordered by recorded_at), POST (create — also mirrors onto Fighter.weight_kg), DELETE.

### 4.4 Sessions — `/sessions`

#### Lifecycle

| Method | Path | Notes |
|---|---|---|
| POST | `/sessions` | Create pending session bound to a fighter |
| GET | `/sessions` | List, optional `?fighter_id=` filter |
| GET | `/sessions/{id}` | One |
| PATCH | `/sessions/{id}` | Update notes |
| DELETE | `/sessions/{id}` | Cascades events + parquet + video |

#### Capture orchestration (CV)

| Method | Path | Notes |
|---|---|---|
| POST | `/sessions/{id}/upload` | Multipart MP4/MOV upload for `uploaded_video` sources |
| POST | `/sessions/{id}/capture/start` | Spawns the daemon thread; returns CaptureStatus |
| POST | `/sessions/{id}/capture/stop` | Signals stop_event |
| POST | `/sessions/{id}/capture/pause` / `.../resume` | Mid-flight pause/resume via pause_event |
| POST | `/sessions/{id}/capture/reprocess` | Wipes prior events, re-runs the pipeline (uploaded_video only) |
| GET | `/sessions/{id}/capture/status` | Polls |
| GET | `/sessions/{id}/preview` | MJPEG stream of the latest annotated frame |

#### Punch events

| Method | Path | Notes |
|---|---|---|
| GET | `/sessions/{id}/events` | All detected punches |
| GET | `/sessions/{id}/events.csv` | CSV export with index, t_ms, time_iso, hand, lead_or_rear, punch_type, velocity_ms, velocity_source, confidence, detected_by |

#### Pre-session HRV baseline

| Method | Path | Notes |
|---|---|---|
| POST | `/sessions/{id}/baseline/upload` | Multipart RR-interval CSV (5-min resting). Computes RMSSD/SDNN/mean_HR over the whole file and persists onto the Session row |

#### Performance

| Method | Path | Notes |
|---|---|---|
| GET | `/sessions/{id}/performance` | Per-session score breakdown — peak_v_p90, ppm, duration_min, score, baselines |

#### Detector evaluation (the dissertation's defensible accuracy path)

| Method | Path | Notes |
|---|---|---|
| GET | `/sessions/{id}/labels` | Read manual `labels.json` from `data/labels/{id}.json` |
| PUT | `/sessions/{id}/labels` | Replace |
| DELETE | `/sessions/{id}/labels` | Drop |
| GET | `/sessions/{id}/evaluation?tolerance_ms=200` | Run match_events + confusion_matrix; returns precision, recall, F1, mean temporal offset, TP/FP/FN counts, per-type confusion |

### 4.5 HRV streaming — `/v2/sessions/{id}/hrv` (Phase 2 surface)

| Method | Path | Notes |
|---|---|---|
| POST | `.../hrv/upload` | Upload an RR-interval CSV (single-column `rr_ms` or `t_ms,rr_ms`) for replay |
| POST | `.../hrv/start` | Spawn replay thread; `?realtime=true` pushes at the source's natural pace, otherwise as fast as possible |
| POST | `.../hrv/stop` | |
| GET | `.../hrv/status` | sample_count + latest metrics window |
| GET | `.../hrv/samples?limit=N` | Recent samples |
| GET | `.../hrv/metrics` | Latest 60-second rolling window (RMSSD/SDNN/mean HR) |
| GET | `.../hrv/live` | **Server-Sent Events** (text/event-stream) — pushes a JSON frame every second with current metrics. Used by the `HrvPanel` component for real-time visualisation |

### 4.6 Per-fighter analytics

| Method | Path | Notes |
|---|---|---|
| GET | `/fighters/{id}/readiness` | Per-fighter z-score readiness (cold-start fallback when N<5 baselines). Returns score, mode (`z_score` / `absolute`), history_n, baseline_mean_ms, baseline_sd_ms, z |
| GET | `/fighters/{id}/matrix` | Per-session points joining resting HRV baseline with CV performance score; computes Pearson r + slope + intercept across sessions |

### 4.7 Medical — `/fighters/{id}/...`

| Method | Path | Notes |
|---|---|---|
| GET | `.../medical` | Read MedicalRecord (or null) |
| PATCH | `.../medical` | Upsert |
| GET/POST/DELETE | `.../allergies[/{id}]` | List + add + remove |
| GET/POST/DELETE | `.../medications[/{id}]` | List + add + remove |
| GET/POST/DELETE | `.../conditions[/{id}]` | List + add + remove |

### 4.8 Team — `/fighters/{id}/...`

| Method | Path | Notes |
|---|---|---|
| GET/POST/DELETE | `.../titles[/{id}]` | Championship belts + amateur titles |
| GET/POST/DELETE | `.../sponsors[/{id}]` | Sponsorships |
| GET/POST/DELETE | `.../coach-assignments[/{id}]` | Many-to-many with Coach profiles |

### 4.9 Static assets

`/static/photos/{fighter|coach|referee}/{id}.{ext}` — profile photos served via FastAPI's `StaticFiles`.

---

## 5. Frontend — every route, tab, and component

[apps/dashboard/](apps/dashboard/) — Next.js 14 App Router.

### 5.1 Routes

| Path | Page |
|---|---|
| `/` | **Roster (home)** — three sections (Fighters / Coaches / Referees) with avatar cards + sign-in/active pills + per-section "+ Create" button |
| `/fighters/[id]` | Fighter Dashboard tab (default landing) |
| `/fighters/[id]/team` | Team tab |
| `/fighters/[id]/sessions` | Sessions tab |
| `/fighters/[id]/hrv` | HRV tab |
| `/fighters/[id]/imu` | IMU tab (placeholder) |
| `/fighters/[id]/medical` | Medical tab |
| `/fighters/[id]/observations` | Observations tab |
| `/fighters/[id]/matrix` | Full HRV-vs-performance scatter (linked from HRV tab) |
| `/coaches/[id]` | Coach detail with sectioned read view + inline edit form |
| `/referees/[id]` | Referee detail (same shape) |
| `/sessions/[id]` | Session detail with capture controls, video preview, pose overlay, punch table, charts, evaluation card |
| `/sessions/new` | Create-session wizard |

### 5.2 Fighter sidebar (FighterSidebar.tsx)

Shows the fighter's avatar + name + nickname + stance, then the seven tab links. Pinned "+ New session" CTA at the bottom.

### 5.3 Per-tab content

#### **Dashboard** ([page.tsx](apps/dashboard/app/fighters/[id]/page.tsx))

- Header: name + nickname + meta + Edit/Delete profile (with typed-name confirm)
- `FighterDashboard` hero: stat cards, Output Index trend chart with latest/vs-prev/avg callouts, ReadinessSidecar
- Aggregate chart row: HandSplitChart (L vs R bar), VelocityDistributionChart (8-bucket histogram, hand-stacked), SessionFrequencyChart (8-week bar)
- Profile sections: Record · Physical · Professional · External IDs
- Weight tracker

#### **Team** ([team/page.tsx](apps/dashboard/app/fighters/[id]/team/page.tsx))

- Bio + Career history (inline editable)
- Gym & coaches: free-text Gym/Trainer + structured CoachAssignment list (real Coach profiles, role pill, current/past, link to coach page)
- Titles: name + organization + weight class + won/lost dates + status pill
- Sponsors: current/past pill + website link + dates

#### **Sessions** ([sessions/page.tsx](apps/dashboard/app/fighters/[id]/sessions/page.tsx))

- Most-recent-session hero card (clickable banner)
- 4-card stat strip (total / completed / punches / active mins)
- Filter pills (all / completed / capturing / pending / failed)
- Rich session list: status pill, source label, RMSSD badge when present, video preview thumbnail, "Open detail" + "Events CSV" actions

#### **HRV** ([hrv/page.tsx](apps/dashboard/app/fighters/[id]/hrv/page.tsx))

- Headline strip: Latest readiness (color-tinted) · Latest RMSSD · Resting HR · HRV-vs-Score r (with strength label gated at n≥10)
- Cold-start banner when readiness is in `absolute` mode
- ReadinessGauge (semicircle, color-coded by zone)
- RmssdTrend (line chart over recorded baselines)
- **HrvScoreScatter** (full-width inline scatter — the dissertation's headline result, with Fisher-z 95% CI annotation)
- Session baselines table
- Polar-H10 roadmap card

#### **IMU** ([imu/page.tsx](apps/dashboard/app/fighters/[id]/imu/page.tsx))

Honest "not wired up yet" placeholder + 6 planned-signals cards (acceleration peak, hand orientation, IMU velocity, impact detection, cadence, asymmetry).

#### **Medical** ([medical/page.tsx](apps/dashboard/app/fighters/[id]/medical/page.tsx))

- **Critical info** red banner — only renders when severe/anaphylactic allergies, active conditions, or active medications exist (ringside-relevant)
- Allergies (severity-tinted pills + add/remove)
- Conditions / history (status-tinted)
- Medications (active/inactive pill + dose/frequency)
- Overview at the bottom (blood type, clearance, primary/emergency contacts, insurance)

#### **Observations** ([observations/page.tsx](apps/dashboard/app/fighters/[id]/observations/page.tsx))

- Headline strip: annotated session count · latest note date · AI recommendations status (violet "coming soon")
- Coach notes timeline (chronological, links to source session)
- AI recommendations placeholder explaining what's needed (10+ sessions with HRV) before honest LLM output is possible

### 5.4 Shared components

| Component | Purpose |
|---|---|
| `AlionLogo` / `AlionWordmark` | Hexagonal shield + "ALION" wordmark |
| `AppShell` (deleted) → `FighterSidebar` | Per-fighter sidebar replaces the global app shell |
| `ProfileAvatar` | Shows photo when present, falls back to gradient initial-letter circle |
| `CreateProfileModal` | Sectioned create form per kind (Fighter: 14 fields; Coach: 17; Referee: 15) with photo upload |
| `FighterDashboard` | Cumulative stats hero + ProgressChart + ReadinessSidecar |
| `AggregateCharts` | HandSplitChart, VelocityDistributionChart, SessionFrequencyChart, HrvScoreScatter |
| `HrvCharts` | ReadinessGauge, HrvMetric, RmssdTrend |
| `HrvPanel` | SSE-driven live-HR sparkline used during HRV replay |
| `EvaluationCard` | Detector-vs-truth precision/recall/F1 + confusion matrix on session detail |
| `PunchChart` / `PunchTimeline` / `VelocityHistogram` / `Sparkline` | Per-session visualisations |

### 5.5 Profile-picker auth

`lib/activeProfile.ts` — localStorage-backed `useActiveProfile()` hook. No real auth (single-user dissertation tool); a "sign out" link top-right of the roster clears the active profile.

### 5.6 OpenAPI → TS codegen

`pnpm gen:api` runs `openapi-typescript` against `http://localhost:8000/openapi.json` and writes `lib/api-schema.ts`. `lib/api-types.ts` re-exports the schemas worth surfacing under stable names. Hand-written interfaces in `lib/api.ts` are migrated gradually; new entities use the generated types.

---

## 6. Algorithms & analytics

### 6.1 Heuristic punch detector — [packages/analyze/punch_detector_heuristic.py](packages/analyze/punch_detector_heuristic.py)

Per-frame algorithm tracking each wrist's velocity over time. Fires a punch event when:

1. Velocity exceeds threshold (configurable, default ~3 m/s with world-coords, fallback ~1.5 with image plane)
2. Peak prominence above local noise floor
3. Post-peak retraction within ~150 ms (separates a punch from a stationary hand)
4. Hand extension relative to shoulder (filters out hands at rest near the body)
5. Refractory window between events on the same hand (default 200 ms)

Outputs `PunchEvent` rows with `t_ms`, `hand`, `velocity_ms`, `velocity_source` (world or image_heuristic), `confidence`. Records "near-miss" reasons (rejected peaks) for tuning.

User-reported accuracy: ~30–40% off in the wild. **Real evaluation requires uploading a `labels.json` and running `scripts/evaluate.py`** — see §7.

### 6.2 Punch-type classifier — [packages/analyze/punch_type_heuristic.py](packages/analyze/punch_type_heuristic.py)

Per-event classifier looking at the wrist's trajectory in the rolling pose history (~last 8 frames):

- Vertical-up trajectory → **uppercut**
- Horizontal across the body → **hook**
- Forward extension along the punch axis → **jab** (lead) or **cross** (rear, derived from stance)

Brittle. Often returns None for ambiguous trajectories.

### 6.3 Velocity refiner — [packages/analyze/velocity_refiner.py](packages/analyze/velocity_refiner.py)

Catmull-Rom spline interpolation over the wrist's recent (t_ms, x, y, z) samples. When the detector reports a peak velocity, the refiner interpolates between frames to estimate the sub-frame peak. If the refined peak is higher than the per-frame estimate, it replaces the original (the rationale: 30 fps undersamples a 50–150 ms punch).

### 6.4 HRV metrics — [packages/analyze/hrv_metrics.py](packages/analyze/hrv_metrics.py)

Standard time-domain HRV (1996 Task Force guidelines). All deterministic arithmetic, no AI:

- `mean_hr_bpm` — `mean(60_000 / rr_ms)`
- `rmssd_ms` — `sqrt(mean((rr[i] − rr[i−1])²))`
- `sdnn_ms` — `stdev(rr_ms)`

`RollingHRMetrics` is a sliding 60-second window used by the live SSE stream.

### 6.5 Performance score / "Output Index" — [packages/analyze/performance.py](packages/analyze/performance.py)

```
score = peak_velocity_p90 × (ppm / 60) × duration_min
```

**Honest framing**: this has no clean physical units (m/s × punches/min × min). It's a session-ranking number, not a measurement. Labeled "ad-hoc ranking · not a physical metric" everywhere it appears in the UI. Replace with a literature-backed metric before defending in the dissertation.

### 6.6 Readiness — [packages/analyze/readiness.py](packages/analyze/readiness.py)

Per-fighter z-score against the fighter's own RMSSD history when ≥5 baselines exist:

```
z = (rmssd − mean(history)) / stdev(history)
score = clamp(50 + 12.5 × z, 0, 100)
```

Cold-start fallback (N < 5): legacy `clamp((rmssd − 20) / 70) × 100`. The mode (`z_score` / `absolute`) is exposed by the API and displayed honestly in the UI (cold-start banner, "calibrated" suffix).

### 6.7 Evaluation — [packages/studies/evaluation.py](packages/studies/evaluation.py)

Greedy time-window matching of detector output against manually-labeled ground truth:

```
For each labeled punch (chronological):
  find earliest UNMATCHED detection within ±tolerance_ms (default 200) on the same hand
  pair them as a true-positive
truth without match → false negative
detection without match → false positive
```

Functions: `match_events`, `confusion_matrix`, `per_class_metrics`, `render_report` (markdown output suitable for the thesis appendix), `load_labels`. 11 unit tests in [tests/unit/test_evaluation.py](tests/unit/test_evaluation.py).

The endpoint `GET /sessions/{id}/evaluation` runs all of this and returns precision, recall, F1, mean temporal offset, per-type confusion. The session detail page surfaces it via `EvaluationCard.tsx`.

---

## 7. CLI scripts

| Script | Purpose |
|---|---|
| `scripts/check_camera.py` | Probe MediaPipe + OpenCV install + enumerate cameras |
| `scripts/record_live.py --fighter <UUID>` | Synchronous live-webcam capture (alternative to the API path; useful when the API is in a Docker container without webcam access) |
| `scripts/process_video.py path/to/clip.mp4 --fighter <UUID>` | Synchronous video processing |
| `scripts/evaluate.py --session <UUID> --labels path/to/labels.json [--tolerance-ms 200] [--out report.md]` | Read manual labels.json, fetch detections from DB, render markdown precision/recall/F1 report |
| `scripts/wipe_data.py [--yes] [--keep-photos]` | **IRB kill switch**. Requires typed `DELETE EVERYTHING` confirmation. Drops sqlite DB + `data/raw` + `data/processed` + `data/photos` (or all but photos), re-creates empty schema |

---

## 8. Cross-modality alignment (SessionClock)

[packages/common/time_utils.py](packages/common/time_utils.py).

`SessionClock.start()` captures two anchors at the moment a session transitions to CAPTURING:

- `wall_t0` — UTC datetime, matches `Session.started_at` so artifacts can be re-aligned across restarts
- `monotonic_ns_t0` — `time.monotonic_ns()`, NTP-immune for in-process events

API:

- `now_offset_ms()` — current offset from T₀ (in-process, monotonic)
- `offset_from_monotonic_ns(ns)` — convert any `time.monotonic_ns()` reading
- `offset_from_wall(dt)` — convert externally-stamped wall-clock instants (e.g. Polar H10 BLE arrivals)
- `wall_for_offset(ms)` — invert

Stored in `api/services/capture_runner.py`'s `_session_clocks` dict and exposed via `clock_for(session_id)`. Future HRV-BLE and IMU drivers fetch this clock to tag every sample with offsets relative to the same instant — the precondition for "HR at impact" cross-modality questions.

See [ADR 006](decisions/006-session-clock-t-zero.md) for the full reasoning.

---

## 9. Migrations history

Located in [migrations/versions/](migrations/versions/). All additive, all downgrade-safe.

| Revision | Title | Adds |
|---|---|---|
| `6554ed244684` | Phase 1 baseline | Fighter, Session, PunchEvent, HRSample, WeighIn |
| `1f0501f1da74` | punch_type column | `PunchEvent.punch_type` |
| `bcaa63d4ff90` | Session HRV baseline | `Session.baseline_*` |
| `bd10d9e3e9bb` | Coaches, referees, medical | Coach, Referee, MedicalRecord, Allergy, Medication, MedicalCondition, photo_path on Fighter |
| `0092952195cf` | Coach + referee extension | dob/nationality/sex/email/phone + coaching_level + certifications + license + languages + notable_fighters/bouts |
| `61d4935702b2` | Fighter team | bio + career_history + FighterTitle + FighterSponsor + CoachAssignment |

Run forward: `uv run alembic upgrade head`. Run back one step: `uv run alembic downgrade -1`.

---

## 10. ADRs (architecture decisions)

[decisions/](decisions/) — short markdown files documenting non-obvious calls.

- [001 — Module boundaries](decisions/001-module-boundaries.md) — hexagonal layout, import-linter contract
- [002 — Encryption deferred](decisions/002-encryption-deferred.md) — IRB-aligned reasoning for plaintext SQLite
- [003 — CV velocity scope amendment](decisions/003-cv-velocity-scope-amendment.md) — world coords vs image plane
- [004 — Phase isolation hardening](decisions/004-phase-isolation-hardening.md) — /v1 freeze + /v2 carve-out
- [005 — Additive fields on /v1](decisions/005-additive-fields-on-v1.md) — when adding to a frozen surface is OK
- [006 — SessionClock T₀](decisions/006-session-clock-t-zero.md) — single anchor, contract before hardware

---

## 11. Testing strategy

`uv run pytest` — 96 tests, organized:

| Suite | Coverage |
|---|---|
| `tests/unit/test_contracts.py` | Pydantic shapes for cross-module events |
| `tests/unit/test_store_repo.py` | Repo round-trips |
| `tests/unit/test_punch_detector.py` | Heuristic detector unit invariants |
| `tests/unit/test_punch_type_classifier.py` | Punch-type heuristic |
| `tests/unit/test_parquet_roundtrip.py` | Pose parquet write/read |
| `tests/unit/test_velocity_refiner.py` | Catmull-Rom interpolation |
| `tests/unit/test_hrv_replay.py` | RR-CSV parser edge cases |
| `tests/unit/test_performance.py` | compute_score |
| `tests/unit/test_readiness.py` | compute_readiness — z-score + cold-start |
| `tests/unit/test_session_clock.py` | SessionClock anchors + offsets |
| `tests/unit/test_evaluation.py` | match_events + confusion matrix + label loader |
| `tests/integration/test_api_*.py` | API surface shapes (404s, 409s, validation) |

Lint: `uv run ruff check`. Types: `uv run mypy packages`. Architecture: `uv run lint-imports`. Frontend: `pnpm tsc --noEmit`.

---

## 12. Operations

### Local run

```bash
uv sync --extra dev --extra capture
uv run uvicorn api.main:app --reload      # 8000
cd apps/dashboard && pnpm install && pnpm dev   # 3000
```

### Migrations

```bash
uv run alembic upgrade head                            # apply pending
uv run alembic revision -m "describe change"           # generate scaffold
uv run alembic downgrade -1                            # roll back one
```

### Data wipe (IRB)

```bash
uv run python scripts/wipe_data.py            # interactive
uv run python scripts/wipe_data.py --yes      # non-interactive
uv run python scripts/wipe_data.py --keep-photos   # spare photos
```

### Generate TS types after a Pydantic change

```bash
# with API running on 8000
cd apps/dashboard && pnpm gen:api
```

### Detector evaluation

```bash
# 1. Manually label punches in a video → labels.json (array of {t_ms, hand, punch_type})
# 2. Run capture so detections live in the DB
# 3.
uv run python scripts/evaluate.py \
   --session <UUID> \
   --labels labels.json \
   --tolerance-ms 200 \
   --out report.md
```

---

## 13. Known limitations & honest caveats

- **Detector is uncalibrated** — user-reported ~30–40% error. The eval pipeline exists; no labeled video has been processed yet. Until that happens, every punch count in the dashboard inherits unknown error.
- **Output Index has no physical units** — labelled "ad-hoc ranking" everywhere; replace with a literature-backed intensity metric before the defence.
- **Readiness in cold-start mode is universal** — clamp((RMSSD−20)/70) ignores age/sex/training state. Switches to per-fighter z-score after 5+ baselines.
- **Pearson r is gated** — strength label withheld until n≥10; Fisher 95% CI shown when n≥4. Promotes statistical honesty over flashy claims.
- **No real auth** — profile-picker via localStorage. Anyone with the URL can edit any profile. Acceptable for a single-user dissertation tool; not for production.
- **CV pipeline t_ms ≠ SessionClock yet** — adapters will adopt the clock as they land (HRV-BLE first, IMU when integrated). Current alignment is rough (~5 ms typical drift between pipeline start and CAPTURING transition).
- **Free-text fields where structure may be wanted** — Coach.specialties / languages / certifications are comma-separated strings, not sub-tables. Trades query power for migration ease.
- **No weekly/longitudinal trend charts yet** — needs ~5+ sessions per fighter before they're meaningful.
- **Hand-rolled SVG charts** — ProgressChart, RmssdTrend, HrvScoreScatter, etc. are bespoke. Likely candidate for migrating to recharts/visx if maintenance cost outweighs the benefit.
- **No FE tests** — TypeScript catches the type-level errors; visual regression and interaction tests are absent.

---

## 14. Roadmap

### Phase 2 (current) — HRV

- ✅ HRV replay driver + 7 v2/HRV endpoints
- ✅ Per-session baseline upload + readiness derivation
- ✅ HRV-vs-performance scatter + Pearson r with CI
- ⏳ Polar H10 BLE driver (hardware lands 2026-05-16; SessionClock contract is ready)
- ⏳ In-session HR streaming during capture (fusion with CV events)

### Phase 3 — fusion

- HR-at-impact via `clock_for(session_id)`
- Inter-round HR recovery curves
- IMU integration (hardware TBD; `capture/imu/` reserved as a sibling of cv/ and hrv/)

### Phase 4 — coaching layer

- LSTM punch detector trained on labeled video (replaces the heuristic; `detected_by` enum already has `lstm_v1` reserved)
- LLM-based coaching observations (the Observations tab's "AI recommendations" section)
- Multi-fighter coach view (when multiple fighters per coach become common)

### Continuous

- Label real videos and surface real precision/recall via the eval pipeline (the dissertation's defensible accuracy claim)
- Migrate hand-written TS interfaces in `lib/api.ts` to the OpenAPI-generated types
- Replace Output Index with a literature-grounded intensity metric

---

_Last updated: 2026-05-07 (commit `e23e2f7`)._

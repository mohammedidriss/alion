# Multi-Camera Capture — Phased Roadmap

**Goal (all four, per the decision):** cover single-camera blind spots for better punch
detection; enable synchronized multi-angle technique review; and reconstruct true 3D
biomechanics from several views — built as a research-grade subsystem, phased in.

**Guiding principles** (unchanged from the rest of the project):
- **Isolation** — never disturb the working single-camera live path. Everything here is additive.
- **Schema-first** — define the view-tagged contracts before building behavior.
- **ADR per decision** — each phase that makes a real choice gets its own ADR (010, 011, …).
- **Every phase ships value** — you can stop after any phase and have something useful.

## What already exists (so this is an extension, not a rebuild)
- **Shared per-session timebase** — `SessionClock` / single `T_0` (ADR-006). All streams tag against it.
- **Clap sync** — `ClapDetector` records a clap's exact `t_ms`; built for IMU↔CV, reusable camera↔camera.
- **Server-side video pipeline** — `capture_runner` runs pose + punch detection + type classifier over an uploaded video already.
- **A reconciliation pattern** — the fusion layer already merges CV↔IMU (`cv_imu_agreement`); cross-view merge mirrors it.

---

## The phases

| # | Phase | Delivers | Needs | Isolated? |
|---|-------|----------|-------|-----------|
| 0 | View-tagged schema | Data model can represent N views | — | Additive (ADR-005 style) |
| 1 | Multi-view ingestion + per-view detection | Per-angle pose + counts | Phase 0 | Reuses `capture_runner` |
| 2 | Temporal sync (clap) | One shared timeline across views | Phase 1 | Reuses `ClapDetector` |
| 3 | Cross-view reconciliation | One trustworthy count + confidence | Phase 2 | Mirrors CV↔IMU fusion |
| 4 | Multi-angle review UI | Synced side-by-side video for coaching | Phase 2 | Dashboard only |
| 5 | Camera calibration | Known camera geometry | — (one-time) | New, self-contained |
| 6 | 3D triangulation + biomechanics | True metric 3D skeleton | Phases 2 + 5 | New analyze module |

### Phase 0 — Foundation: view-tagged schema *(small, enabling)*
Add a `CameraView` (id, `session_id`, label like `front`/`side`/`45-left`/`overhead`). Tag
`PoseFrame` and `PunchEvent` with a nullable `view_id` (additive → single-cam stays on v1,
`view_id` defaults to a "primary" view). Store pose/video **per view** (`{session}.{view}.pose.parquet`).
*No behavior change* — just the ability to represent multiple views.

### Phase 1 — Multi-view ingestion + per-view detection *(the offline multi-video path)*
Allow N video uploads per session, each labeled with its view. `capture_runner` already analyzes
one video; loop it over the views, tagging outputs with `view_id`. **Deliverable:** upload 2–3
angle videos → per-view pose + per-view punch counts, each independently inspectable.

### Phase 2 — Temporal sync (clap alignment)
Fighter claps at the start (visible to all cameras). `ClapDetector` finds each view's clap `t_ms`;
compute per-view offset → align every view to the shared `T_0`. Fallbacks when a view misses the
clap: a visible countdown/flash, or manual nudge. **Deliverable:** all views on one timeline (±1 frame).

### Phase 3 — Cross-view reconciliation *(delivers "better punch detection")*
Merge per-view detections: the same punch seen by multiple views (aligned time + hand) = one punch.
**Union** across views raises recall (a punch thrown into camera A is side-on to camera B);
**agreement** across views raises confidence. Report per-view counts, a **consensus count**, and
inter-camera agreement — the same shape as the existing `cv_imu_agreement`.

### Phase 4 — Multi-angle review UI *(delivers "technique review")*
Session page: synchronized side-by-side players (aligned by Phase-2 offsets) with a shared scrubber,
per-view + consensus counts, and the timeline. **Deliverable:** coach watches front + side in lockstep.

### Phase 5 — Camera calibration *(gateway to 3D)*
One-time per rig: **intrinsics** (each camera, checkerboard) + **extrinsics** (relative poses via a
shared checkerboard/ChArUco or a wand). Store a calibration per rig/session. Standard OpenCV.

### Phase 6 — 3D triangulation + biomechanics *(delivers "true 3D")*
Triangulate the per-view 2D keypoints on synced frames → a **true metric 3D skeleton** (linear/DLT
triangulation + RANSAC across views). Compute real joint angles, segment velocities, and punch
trajectories in metres. Re-run detection/classification on the true 3D (beats MediaPipe's single-view
estimate) — and it **cross-validates the IMU**.

---

## Equipment & setup (practical)
- **Cameras:** start with **2** — front + one side at ~90° — for reconciliation. Add **45° and/or
  overhead** (3–4 total) for robust 3D. Any devices work (phones, webcams); match frame rate,
  prefer **60 fps** for 3D at boxing speeds.
- **Placement:** surround the fighter (~2–3 m, upper-body framing). Avoid all-frontal — triangulation
  needs angular diversity.
- **Calibration target (Phase 5+):** printed **checkerboard (e.g. 9×6)** or ChArUco, held visible to
  overlapping views.
- **Sync marker:** a **clap** at the start (and periodically) — reuse `ClapDetector`. No genlock needed
  for Phases 1–4; clap-sync + 60 fps is enough for 3D of boxing motion.

## Dissertation angle (this is a contribution, not just plumbing)
- **RQ (detection):** *Does multi-view fusion improve punch-detection recall/precision vs a single view?*
  → measured at Phase 3, against your labeled sessions.
- **RQ (kinematics):** *How does markerless multi-view 3D kinematics compare to IMU-derived and
  single-view estimates?* → Phase 6, with the IMU as an independent reference.
- Markerless multi-view 3D capture for combat sports is publishable in its own right.

## Recommended sequencing (with the IMU mid-flight)
Phases 0–4 are independent of calibration and the IMU, and each ships value. The efficient move:
**fold Phases 0–1 into the upcoming IMU controlled sessions** — record the same punches from
several angles *while* the fighter wears the IMU. That single, richly-labeled dataset then serves
punch-detection accuracy (Phase 3), multi-angle review (Phase 4), *and* IMU ground-truth at once.
Phases 5–6 (the 3D leg) come after, when you're ready to make 3D reconstruction its own study.

**Immediate first step when you choose to start:** ADR-010 + Phase 0 schema — the small, isolated
enabling change that unlocks everything else without touching the working single-camera path.

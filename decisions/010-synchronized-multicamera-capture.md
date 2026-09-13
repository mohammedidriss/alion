# 010. Synchronized multi-device capture — coordinator + capture-node protocol

- **Status**: Accepted
- **Date**: 2026-09-13
- **Phase**: 4 (multi-camera capture)

## Context

We want to record one session from **multiple cameras at once** (e.g. 3 phones at
different angles) plus the existing Polar H10, evaluate the fighter from several
views, and — later — reconstruct true 3D. The full arc is laid out in
`docs/MULTICAM_ROADMAP.md`; this ADR decides the **capture and synchronization
substrate** that everything else sits on. Calibration and 3D triangulation are
explicitly out of scope here (a later ADR).

Requirements gathered from the coach's workflow:

- Cameras and the Polar **register to the server and appear on the session page**
  as devices; the coach clicks **one** *Start session* and they all begin together.
- **No manual clip-syncing or editing.** Alignment must be automatic.
- The real-world sync marker is the **ring bell**, not a clap (a clap "isn't always
  workable"). Audio is always present in a bout.
- Goals span better punch detection, synchronized multi-angle review, and (later)
  3D — so the substrate must be defensible enough for research, not just a demo.

Hard constraints:

- **Phones cannot be frame-genlocked.** Independent oscillators; even "same fps"
  drifts. Frame-perfect hardware sync is off the table with consumer devices.
- **Browser camera access needs a secure context** — `getUserMedia` requires HTTPS
  (or localhost). On a gym LAN at `http://192.168.x.x` phones will refuse the
  camera. `BrowserCapture.tsx` already notes this ("mediaDevices can be undefined
  in non-secure context").
- We already have the alignment foundation: `SessionClock`/T_0 (ADR-006), an
  **SSE** live channel (`hrv.py` `stream_router`), a device-card pattern
  (`PolarH10Card` + `getPairedDevice`, started on session start via
  `api.startHrvBle`), the in-browser MediaPipe pipeline (`BrowserCapture`), and a
  clap/impulse detector (`ClapDetector`). This ADR should *reuse* these, not
  reinvent them.

The tempting shortcut is "make the dashboard both master page and slave page." It
works, but it hard-wires capture into the dashboard and keeps every modality
(CV/HRV/IMU) bespoke. We want the seam placed so new device *types* cost an
adapter, not a rewrite — the same ports-and-adapters discipline ADR-001 already
enforces for the analyze layer.

## Decision

Introduce a **device-agnostic capture-node protocol (a port)** and a **session
coordinator (the master)**. Any device that speaks the protocol is a capture node;
the coordinator neither knows nor cares what a node internally is. The browser
camera page is simply **adapter #1**.

**The capture-node protocol (the port).** A small, versioned contract in the
`contracts` package, transport-independent:

- `register(session_id, node_type, capabilities, view_label) -> device_id`
- `sync_clock()` — repeatable NTP-style round-trips; the node estimates its offset
  to the coordinator's master clock (which anchors `SessionClock`, ADR-006).
- **command subscription** — `arm`, `start(at=T)`, `stop`, `marker(kind)`.
- `heartbeat(device_id, status)` — `connected | ready | recording | error`.
- `upload(device_id, artifact, timestamps)` / streamed frames, tagged by `device_id`.

**The coordinator (the master).** Extends the session's existing device concept in
the `api` composition root (where active-session state already lives alongside
`_session_clocks`). It owns: a per-session **device registry**; a **clock-sync**
endpoint; a **command bus** that broadcasts lifecycle commands; and **tagged
ingestion**. *Start session* computes `T = now + Δ` (a few seconds) on the master
clock and broadcasts `start(at=T)` to every registered node **and** the Polar
start it already fires — one action, everything begins.

**Transport (v1): reuse what exists.** Server→node commands ride **SSE** (same
channel HRV already uses); node→server (register, clock-sync, heartbeat, upload) is
plain **HTTP POST**. The *contract* is stable, so a later move to WebSocket/MQTT
touches transport only, not device logic.

**The sync stack (layered; each tighter).** Per ADR-006's philosophy, the real
guarantee is *timestamps on one clock*, not identical start frames:

1. **NTP-style clock sync** → nodes agree with the master clock (~ms over WiFi).
2. **Scheduled `start(at=T)`** + camera pre-warm → nodes begin together, click-and-go.
3. **Per-frame timestamps on the shared clock** → alignment is timestamp-matching,
   automatic. *This is the guarantee.*
4. **Audio/bell refinement** → cross-correlate the bell (a loud, sharp transient) or
   any shared ambient sound across node microphones for sub-frame cross-check.
   Generalizes `ClapDetector` from a gesture to an audio impulse.

This yields **frame-accurate-enough** capture for reconciliation, review, and 60 fps
3D — explicitly *not* genlock-perfect.

**Schema (additive, ADR-005).** A `CaptureDevice` / `CameraView` (id, session,
`node_type`, `view_label`) and a nullable `device_id` / `view_id` tag on
`PoseFrame`, `PunchEvent`, and stored artifacts. Single-camera sessions keep working
unchanged (a default "primary" view); this is roadmap Phase 0.

**Isolation.** The existing single-camera live path and every current contract are
untouched. `import-linter` boundaries hold: the port lives in `contracts`, the
coordinator in the `api` composition root, each adapter behind the port. Adding the
IMU or a Pi rig later cannot break the camera path (ADR-001).

**MVP scope for the first implementation:** coordinator (registry + clock-sync +
`start(at=T)` over SSE + tagged upload) and the **browser camera adapter**. Audio/bell
refinement and cross-view reconciliation are fast-follows; native-app and headless
Pi-agent adapters, calibration, and 3D are later ADRs.

## Alternatives considered

- **Dashboard as master-page + slave-page, no protocol seam** — rejected. Simpler
  to start, but hard-wires capture into the dashboard, keeps CV/HRV/IMU bespoke, and
  makes each new device type a code change in the core. The protocol costs a little
  design up front and the browser MVP is the *same* effort behind a port.
- **Two separate native apps (manager + camera)** — rejected for now. 2× build,
  installs on every device, app-store friction, no benefit the browser adapter
  doesn't give. A native adapter can arrive later behind the same protocol.
- **WebRTC live-streaming from phones** — rejected for capture: lossy and complex;
  research wants full-quality on-device recording + timestamped upload. Could return
  later as a "live monitor" node.
- **Naive `start-now` broadcast (no clock-sync, no per-frame stamps)** — rejected:
  per-device network + camera latency makes it tens of ms off with no way to correct.
  The value is in the shared-clock timestamps, not the broadcast instant.
- **PTP / hardware genlock** — deferred. Sub-microsecond but needs network/hardware
  support. NTP-over-WiFi is pragmatic; the protocol leaves room to add PTP for a
  fixed rig if a future 3D study demands it.
- **Clap gesture as the sync marker** — rejected per the coach: not always workable.
  Audio-impulse (bell) sync subsumes it and is automatic.

## Consequences

- **Positive**:
  - New device *types* cost an adapter, not a core change — the ADR-001 pattern
    applied to capture. Phones, a native app, a Raspberry-Pi webcam rig, and the
    existing Polar/IMU BLE adapters all become nodes on **one** registry + command bus.
  - Synchronized start is a single coach action; alignment is deterministic
    timestamp arithmetic (the ADR-006 win, extended to N cameras).
  - The browser adapter ships first with no extra MVP cost; a fixed Pi rig (locked
    settings, reliable timestamps) can drop in later for research-grade 3D with no
    rework.
  - Unifies the multi-modal vision instead of bolting on a one-off camera feature.
- **Negative / risks**:
  - **HTTPS on the LAN is required** for browser cameras (secure context) — a
    real one-time setup (self-signed / `mkcert`). Native/Pi adapters avoid it.
  - **Mobile-browser limits**: weaker exposure/focus/fps locking and background-tab
    throttling. Fine for a controlled, screen-on recording; the native/Pi adapter is
    the escape hatch, same protocol.
  - **Sync precision is ~ms (NTP-over-WiFi), not genlock.** Adequate for the goals
    but must be **measured, not assumed** (cf. the IMU rate check).
  - **Clock drift** over a round → re-anchor with a periodic bell/marker.
  - SSE reconnection/roster churn (a phone drops mid-session) needs graceful handling.
- **Follow-ups**:
  - **Measure** real 3-phone sync precision on the bench before trusting it
    (build the contract, measure first).
  - Decide: is the ring bell **ambient-only** (sync marker) or **electronic**
    (the coordinator can trigger it as the start signal)? Shapes the trigger.
  - ADR-011: cross-view reconciliation (consensus count, inter-camera agreement,
    mirroring the CV↔IMU pattern).
  - ADR-012: camera calibration + 3D triangulation.
  - Fold the existing Polar/IMU BLE adapters into the unified device registry.
  - Add native-app / headless Pi-agent adapters if browser limits bite.

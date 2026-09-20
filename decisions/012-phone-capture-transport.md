# 012. Phone capture transport — Wi-Fi for video, Bluetooth as control only, native app for deployment

- **Status**: Proposed
- **Date**: 2026-09-20
- **Phase**: 4 (capture substrate) → field deployment

## Context

Phones are our multi-camera capture nodes (ADR-010). Today each phone joins a
session by scanning a QR code, which opens a **browser page** (`CameraNode` /
`/sessions/[id]/camera`); the page uses `getUserMedia` + `MediaRecorder` +
in-browser MediaPipe, and talks to the server over **Wi-Fi/HTTP** through the
same-origin `/api` proxy — register, heartbeat, ~1 fps preview frames, and the
per-device clip + pose upload on stop.

The recurring question from the coach: *can we connect the phone over **Bluetooth**
— like the Polar H10 HRV strap — and move the video over **Wi-Fi**?* It's a good
instinct, but it rests on a category error worth settling on the record.

**A phone camera is a *source*, not a *sensor*.** The Polar is a peripheral the
computer connects *to* over BLE; it emits a few bytes per second (a heart-rate
number). BLE is designed for exactly that — ~100–250 kbps practical, low power.
A phone camera produces the opposite: a high-bandwidth stream (1080p ≈ several to
tens of Mbps). **BLE cannot carry video — it's ~100× too slow.** Classic Bluetooth
is faster but still far short, and iOS won't expose it for this. So the two halves
separate cleanly: **video must go over Wi-Fi (or USB); Bluetooth can only ever be a
control channel** (start/stop, identity, live counts).

Two more constraints kill the *browser* Bluetooth idea specifically:

- **iOS Safari has no Web Bluetooth at all.** (Chrome/Android support it partially.)
- Web Bluetooth is **central-only** — a page can connect *out* to a peripheral, but
  cannot make the phone *be* a peripheral the server connects to (the Polar model).
  That needs OS-level access, i.e. a native app.

And the real friction in the current flow is **not** the transport — it's that
browser camera access (`getUserMedia`) requires a **secure context (HTTPS with a
*trusted* cert)**, which drove the whole certificate/tunnel saga. BLE would not
remove that; only leaving the browser does.

ADR-010 already anticipated this: it defines a **device-agnostic capture-node
protocol**, with the browser page as "adapter #1." A native app is simply adapter
#2 speaking the same protocol — so this decision is about *which clients we build*,
not a re-architecture.

## Decision

Adopt a **phased** phone-capture architecture. Video always travels over Wi-Fi;
Bluetooth, if used at all, is a control channel and only inside a native app.

1. **Video/streaming stays on Wi-Fi** — permanently. It is the only viable transport
   for a phone's camera feed, and it is already what we do. Bluetooth is never a
   video path.

2. **Phase A — now (prototype / dissertation validation): keep the browser page, and
   remove the real friction with a trusted cert.** Install a local CA (mkcert) once
   and trust it on each capture phone; the QR-join flow then "just works" with no
   cert warnings and no tunnel. This is a one-time, low-effort fix that resolves the
   actual pain (`getUserMedia` secure context) without BLE or an app.

3. **Phase B — field deployment: a native capture app is the target.** It gives the
   coach's exact model — **BLE for pairing/discovery/identity/control, Wi-Fi for
   video** — and as a side effect eliminates the HTTPS/secure-context problem
   entirely (native camera access), with better performance (hardware encoding) and
   reliability. It implements the ADR-010 node protocol, so the coordinator and the
   whole server side are unchanged.

4. **Do not build the native app until the science is proven.** The web path is
   sufficient to validate the research questions. The app is a deployment
   investment, deferred behind the prototype.

## Alternatives considered

- **Bluetooth for the video itself** — rejected on physics. BLE bandwidth is ~100×
  short of live video; Classic Bluetooth still far short and unavailable on iOS for
  this. No amount of engineering closes that gap.
- **Web Bluetooth for pairing/control in the browser** — rejected. Absent on iOS
  Safari, central-only elsewhere (can't make the phone a peripheral), and it does
  nothing for the camera/HTTPS problem that is the actual friction.
- **Public tunnel (cloudflared / trycloudflare) for reachability + TLS** — rejected;
  the coach already removed it. It routes gym video through a third-party public
  domain, adds an external dependency, and isn't appropriate for a LAN capture rig.
- **USB tethering** — rejected. Cables to 3 phones around a ring is impractical, and
  it defeats the point of wireless capture nodes.
- **Build the native app now** — rejected as premature. Real, ongoing effort (iOS +
  Android, dev accounts, sideload/TestFlight, maintenance) before the prototype has
  earned it. Phase B, not Phase A.

## Consequences

- **Positive**
  - The Wi-Fi-for-video half is correct and already built — no rework.
  - Phase A removes the certificate pain with a one-time mkcert install, no BLE, no
    tunnel, no app.
  - The coach's BLE-pair + Wi-Fi-video model is recorded as the deployment target,
    reachable via the native app rather than lost.
  - Because it implements the ADR-010 node protocol, the native app is additive —
    the coordinator, fusion, and dashboard don't change.
  - Phasing avoids sinking app-development cost before the research is validated.

- **Negative / risks**
  - Two capture clients eventually coexist (web + native). Mitigation: hold the
    ADR-010 node protocol stable so each is "just another node"; the web page stays
    the zero-install fallback.
  - The native app is genuine ongoing effort (two platforms, store/sideload, dev
    accounts, updates) — accepted, and deferred to deployment.
  - The trusted cert must be installed per capture phone (one-time, documented).

- **Follow-ups**
  - Phase A: generate a local CA with mkcert, trust it on the capture phones, and
    document the QR-join flow without cert warnings.
  - Phase B (when deploying): a dedicated native-app ADR specifying the BLE control
    profile (pairing, identity, start/stop, live counts) and the Wi-Fi video
    transport (chunked upload vs. WebRTC/RTSP live), both conforming to the ADR-010
    node protocol.
  - Keep `CameraNode` and the coordinator contract stable so the native app drops in
    as adapter #2.

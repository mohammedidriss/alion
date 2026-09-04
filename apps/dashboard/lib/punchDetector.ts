/**
 * Client-side punch detector — TypeScript port of
 * packages/analyze/punch_detector_extension.py (ADR 009).
 *
 * Runs in the browser on MediaPipe PoseLandmarker output during live webcam
 * capture; detected events are bulk-uploaded to the API. This is the detector
 * that actually governs the live punch count.
 *
 * A punch is counted only on a genuine ballistic out-and-back wrist excursion
 * (hysteresis peak detection over the wrist→shoulder extension, with ballistic
 * peak-speed as the primary gate). This replaced a velocity-peak heuristic that
 * counted every wrist blip — precision 0.05 on labeled ground truth (84
 * detections for 4 real punches); a still session logged 26, a 10-punch session
 * 39. See ADR 009 for the validation.
 */

import type { PunchType } from "./api";

// MediaPipe landmark indices
const LM_LEFT_SHOULDER = 11;
const LM_RIGHT_SHOULDER = 12;
const LM_LEFT_ELBOW = 13;
const LM_RIGHT_ELBOW = 14;
const LM_LEFT_WRIST = 15;
const LM_RIGHT_WRIST = 16;

// Defaults mirror the Python reference (validated on real sessions). The
// excursion gate catches wide/side punches; the elbow-extension gate is
// direction-invariant and catches straight punches thrown toward the camera
// (whose forward motion the monocular depth axis compresses). Keep in sync with
// packages/analyze/punch_detector_extension.py (ADR 009).
const MIN_PEAK_VELOCITY_MS = 2.2; // 1.2 caught everything; 3.0 missed depth-axis punches
const MIN_EXCURSION_M = 0.04; // min wrist travel valley→peak, metres (world coords)
const HYSTERESIS_M = 0.03; // turn-around must exceed this to confirm a peak/valley
const REFRACTORY_MS = 250;
const MIN_VISIBILITY = 0.5;
const LEGACY_BODY_WIDTH = 0.45; // 2D-fallback scale (no world landmarks)
// Elbow-extension gate.
const ELBOW_CHAMBER_DEG = 100; // elbow counts as "bent" below this
const ELBOW_EXTEND_DEG = 150; // ...and "straight" above this
const ELBOW_WINDOW_MS = 200; // bent→straight must happen within this window (punch tempo)
// Upward-drive gate — the uppercut. Brings the fist up with the arm bent and
// close to the body, so neither other gate sees it.
const UP_MIN_SPEED_MS = 2.0;
const UP_MIN_RISE_M = 0.13;
const UP_START_BELOW_M = 0.05;
const UP_WINDOW_MS = 250;
// Opposite-hand suppression: a near-simultaneous fire on the other hand is
// almost always body sway on both wrists, not a real second punch.
const OPP_HAND_SUPPRESS_MS = 130;

export type Hand = "left" | "right";

export interface PunchEvent {
  t_ms: number;
  hand: Hand;
  velocity_ms: number;
  confidence: number;
  detected_by: string;
  lead_or_rear: "lead" | "rear" | null;
  velocity_source: string;
  // Set by the caller after detection via classifyPunchType(); the gates
  // themselves are detection-only (kept in sync with the Python detector).
  punch_type: PunchType | null;
}

type Vec3 = [number, number, number];

interface Landmark {
  x: number;
  y: number;
  z: number;
  visibility?: number;
}

/** Per-hand state: wrist-excursion hysteresis tracker + elbow-extension tracker. */
interface HandCycle {
  goingUp: boolean;
  extreme: number | null; // current local extreme (peak while up, valley while down)
  chamber: number | null; // last confirmed valley — the excursion baseline
  risePeakSpeed: number;
  peakT: number;
  lastPos: Vec3 | null;
  lastT: number | null;
  lastEventT: number | null; // shared refractory across all gates
  elbowHist: Array<[number, number]>; // recent (t_ms, angle) samples for the tempo window
  elbowExtended: boolean; // currently past the extend threshold — needs re-chamber
  yrelHist: Array<[number, number]>; // recent (t_ms, wristY − shoulderY) for the uppercut gate
  uppercutFired: boolean; // currently mid-drive — needs the wrist to stop rising
}

function makeHandCycle(): HandCycle {
  return {
    goingUp: true,
    extreme: null,
    chamber: null,
    risePeakSpeed: 0,
    peakT: 0,
    lastPos: null,
    lastT: null,
    lastEventT: null,
    elbowHist: [],
    elbowExtended: false,
    yrelHist: [],
    uppercutFired: false,
  };
}

function dist(a: Vec3, b: Vec3): number {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
}

function elbowAngleDeg(shoulder: Vec3, elbow: Vec3, wrist: Vec3): number {
  const ux = shoulder[0] - elbow[0],
    uy = shoulder[1] - elbow[1],
    uz = shoulder[2] - elbow[2];
  const vx = wrist[0] - elbow[0],
    vy = wrist[1] - elbow[1],
    vz = wrist[2] - elbow[2];
  const nu = Math.sqrt(ux * ux + uy * uy + uz * uz);
  const nv = Math.sqrt(vx * vx + vy * vy + vz * vz);
  if (nu < 1e-6 || nv < 1e-6) return 180;
  const cosA = Math.max(-1, Math.min(1, (ux * vx + uy * vy + uz * vz) / (nu * nv)));
  return (Math.acos(cosA) * 180) / Math.PI;
}

function getLandmark(lms: Landmark[], idx: number): Landmark | null {
  const lm = lms[idx];
  if (!lm || (lm.visibility ?? 1) < MIN_VISIBILITY) return null;
  return lm;
}

function handToLeadRear(hand: Hand, stance: string | null): "lead" | "rear" | null {
  // Stance may arrive in any case (the DB enum is upper-case "ORTHODOX").
  const s = stance ? stance.toLowerCase() : null;
  if (s === "orthodox") return hand === "left" ? "lead" : "rear";
  if (s === "southpaw") return hand === "right" ? "lead" : "rear";
  return null;
}

function confidence(
  amplitude: number,
  peakSpeed: number,
  minExcursion: number,
  minVelocity: number,
  visibility: number,
): number {
  const ampTerm = Math.min(1, amplitude / (minExcursion * 2));
  const spdTerm = Math.min(1, peakSpeed / (minVelocity * 1.6));
  return Math.max(0.05, Math.min(1, 0.5 * ampTerm + 0.5 * spdTerm) * Math.max(0.2, visibility));
}

export class PunchDetector {
  private stance: string | null;
  private left = makeHandCycle();
  private right = makeHandCycle();
  private lastFireT: number | null = null;
  private lastFireHand: Hand | null = null;

  constructor(stance: string | null = null) {
    this.stance = stance;
  }

  reset() {
    this.left = makeHandCycle();
    this.right = makeHandCycle();
    this.lastFireT = null;
    this.lastFireHand = null;
  }

  /**
   * Feed one frame. Returns detected punch events (0–2 per frame).
   *
   * @param normLms  33 normalised landmarks from PoseLandmarker result
   * @param worldLms 33 world landmarks (optional but preferred)
   * @param tMs      frame timestamp in milliseconds
   */
  feed(normLms: Landmark[], worldLms: Landmark[] | null | undefined, tMs: number): PunchEvent[] {
    const lms = worldLms && worldLms.length === 33 ? worldLms : normLms;
    const useWorld = lms === worldLms;

    const el = this.step(lms, "left", LM_LEFT_WRIST, LM_LEFT_SHOULDER, LM_LEFT_ELBOW, this.left, tMs, useWorld);
    const er = this.step(lms, "right", LM_RIGHT_WRIST, LM_RIGHT_SHOULDER, LM_RIGHT_ELBOW, this.right, tMs, useWorld);
    const events: PunchEvent[] = [];
    for (const ev of [el, er]) {
      if (!ev) continue;
      if (
        this.lastFireT !== null &&
        this.lastFireHand !== null &&
        ev.hand !== this.lastFireHand &&
        ev.t_ms - this.lastFireT < OPP_HAND_SUPPRESS_MS
      ) {
        continue; // sway on the opposite wrist, not a real second punch
      }
      this.lastFireT = ev.t_ms;
      this.lastFireHand = ev.hand;
      events.push(ev);
    }
    return events;
  }

  private step(
    lms: Landmark[],
    hand: Hand,
    wristIdx: number,
    shoulderIdx: number,
    elbowIdx: number,
    cyc: HandCycle,
    tMs: number,
    useWorld: boolean,
  ): PunchEvent | null {
    const wristLm = getLandmark(lms, wristIdx);
    const shLm = getLandmark(lms, shoulderIdx);
    if (!wristLm || !shLm) {
      cyc.lastPos = null;
      cyc.lastT = null;
      return null;
    }

    const wrist: Vec3 = [wristLm.x, wristLm.y, wristLm.z];
    const shoulder: Vec3 = [shLm.x, shLm.y, shLm.z];
    const scale = useWorld ? 1 : LEGACY_BODY_WIDTH;
    const ext = dist(wrist, shoulder) * scale;

    let speed = 0;
    let upSpeed = 0; // upward wrist speed (world Y more negative = up)
    if (cyc.lastPos && cyc.lastT !== null) {
      const dtS = Math.max(1e-3, (tMs - cyc.lastT) / 1000);
      speed = (dist(wrist, cyc.lastPos) * scale) / dtS;
      upSpeed = (-(wrist[1] - cyc.lastPos[1]) * scale) / dtS;
    }
    cyc.lastPos = wrist;
    cyc.lastT = tMs;

    // Bootstrap on the first valid frame.
    if (cyc.extreme === null || cyc.chamber === null) {
      cyc.extreme = ext;
      cyc.chamber = ext;
      cyc.peakT = tMs;
      return null;
    }

    let ev: PunchEvent | null = null;

    if (cyc.goingUp) {
      if (ext > cyc.extreme) {
        cyc.extreme = ext;
        cyc.peakT = tMs;
      }
      cyc.risePeakSpeed = Math.max(cyc.risePeakSpeed, speed);
      // Confirmed turn-around: the peak we were tracking is a local maximum.
      if (ext <= cyc.extreme - HYSTERESIS_M) {
        const amplitude = cyc.extreme - cyc.chamber;
        const spaced =
          cyc.lastEventT === null || cyc.peakT - cyc.lastEventT >= REFRACTORY_MS;
        if (
          amplitude >= MIN_EXCURSION_M &&
          cyc.risePeakSpeed >= MIN_PEAK_VELOCITY_MS &&
          spaced
        ) {
          const vis = Math.min(shLm.visibility ?? 1, wristLm.visibility ?? 1);
          ev = {
            t_ms: cyc.peakT,
            hand,
            velocity_ms: Math.round(cyc.risePeakSpeed * 100) / 100,
            confidence:
              Math.round(
                confidence(amplitude, cyc.risePeakSpeed, MIN_EXCURSION_M, MIN_PEAK_VELOCITY_MS, vis) *
                  100,
              ) / 100,
            detected_by: "heuristic",
            lead_or_rear: handToLeadRear(hand, this.stance),
            velocity_source: useWorld ? "world" : "image_heuristic",
            punch_type: null, // classified by the caller from pose history
          };
          cyc.lastEventT = cyc.peakT;
        }
        cyc.goingUp = false;
        cyc.extreme = ext; // start tracking the following valley
      }
    } else {
      // Tracking a valley.
      if (ext < cyc.extreme) cyc.extreme = ext;
      // Confirmed turn-around: the valley we were tracking is a local minimum.
      if (ext >= cyc.extreme + HYSTERESIS_M) {
        cyc.chamber = cyc.extreme; // this valley is the next punch's baseline
        cyc.goingUp = true;
        cyc.extreme = ext;
        cyc.risePeakSpeed = speed;
        cyc.peakT = tMs;
      }
    }

    // --- Elbow-extension gate: fires when the elbow goes from bent to straight
    // within a short window — a punch tempo. Direction-invariant, so it catches
    // straight punches toward the camera that the excursion gate misses.
    const elLm = getLandmark(lms, elbowIdx);
    if (elLm) {
      const elbowAngle = elbowAngleDeg(shoulder, [elLm.x, elLm.y, elLm.z], wrist);
      cyc.elbowHist.push([tMs, elbowAngle]);
      const cutoff = tMs - ELBOW_WINDOW_MS;
      cyc.elbowHist = cyc.elbowHist.filter(([t]) => t >= cutoff);
      if (elbowAngle <= ELBOW_CHAMBER_DEG) cyc.elbowExtended = false; // re-armed
      const recentMin = Math.min(...cyc.elbowHist.map(([, a]) => a));
      if (
        !cyc.elbowExtended &&
        elbowAngle >= ELBOW_EXTEND_DEG &&
        recentMin <= ELBOW_CHAMBER_DEG // was bent within the window
      ) {
        const spaced =
          cyc.lastEventT === null || tMs - cyc.lastEventT >= REFRACTORY_MS;
        if (ev === null && spaced) {
          ev = {
            t_ms: tMs,
            hand,
            velocity_ms: Math.round(speed * 100) / 100,
            confidence: 0.6,
            detected_by: "heuristic",
            lead_or_rear: handToLeadRear(hand, this.stance),
            velocity_source: useWorld ? "world" : "image_heuristic",
            punch_type: null, // classified by the caller from pose history
          };
          cyc.lastEventT = tMs;
        }
        cyc.elbowExtended = true; // require re-chamber before the next elbow fire
      }
    }

    // --- Upward-drive gate (uppercut): a fast upward wrist drive that started
    // from below the shoulder. Covers the punch neither other gate sees.
    const yrel = (wrist[1] - shoulder[1]) * scale; // + = wrist below the shoulder
    cyc.yrelHist.push([tMs, yrel]);
    const upCutoff = tMs - UP_WINDOW_MS;
    cyc.yrelHist = cyc.yrelHist.filter(([t]) => t >= upCutoff);
    if (upSpeed <= 0) cyc.uppercutFired = false; // reset once the wrist stops rising
    const low = Math.max(...cyc.yrelHist.map(([, y]) => y)); // most-below point in window
    const risen = low - yrel;
    if (
      ev === null &&
      !cyc.uppercutFired &&
      upSpeed >= UP_MIN_SPEED_MS &&
      risen >= UP_MIN_RISE_M &&
      low >= UP_START_BELOW_M
    ) {
      const spaced = cyc.lastEventT === null || tMs - cyc.lastEventT >= REFRACTORY_MS;
      if (spaced) {
        ev = {
          t_ms: tMs,
          hand,
          velocity_ms: Math.round(upSpeed * 100) / 100,
          confidence: 0.6,
          detected_by: "heuristic",
          lead_or_rear: handToLeadRear(hand, this.stance),
          velocity_source: useWorld ? "world" : "image_heuristic",
          punch_type: null, // classified by the caller from pose history
        };
        cyc.lastEventT = tMs;
      }
      cyc.uppercutFired = true;
    }

    return ev;
  }
}

// --- Punch-type classifier -------------------------------------------------
// TypeScript port of analyze/punch_type_heuristic.classify_punch_type — MUST
// stay in sync with it (ADR 009). Runs *after* the detector has decided a punch
// happened: it reads the wrist's 3D trajectory over the last few pose frames and
// labels the type from the dominant motion axis + stance. v0.5 — replaced later
// by the IMU/LSTM. Frames are the rolling pose buffer (newest last), each with
// `landmarks`/`world_landmarks` as 33 × [x, y, z, visibility].
const HOOK_LATERAL_RATIO = 1.2; // |Δx| must dominate |Δz| by this to call it a hook
const UPPERCUT_VERTICAL_RATIO = 1.4; // upward |Δy| must dominate this much
const CLASSIFY_LOOKBACK = 5; // frames of history to read the trajectory from

interface PoseHistoryFrame {
  landmarks: number[][];
  world_landmarks: number[][] | null;
}

export function classifyPunchType(
  history: PoseHistoryFrame[],
  hand: Hand,
  stance: string | null,
): PunchType | null {
  if (history.length < 2) return null;
  const tail = history.slice(-CLASSIFY_LOOKBACK);
  if (tail.length < 2) return null;

  const wristIdx = hand === "left" ? LM_LEFT_WRIST : LM_RIGHT_WRIST;
  const useWorld = tail.every((f) => f.world_landmarks != null);
  const wristXyz = (f: PoseHistoryFrame): Vec3 | null => {
    const src = useWorld ? f.world_landmarks! : f.landmarks;
    const w = src[wristIdx];
    if (!w) return null;
    if ((w[3] ?? 1) < 0.4) return null; // wrist visibility too low
    return [w[0], w[1], w[2]];
  };

  const start = wristXyz(tail[0]);
  const end = wristXyz(tail[tail.length - 1]);
  if (!start || !end) return null;

  const dx = end[0] - start[0]; // lateral
  const dy = end[1] - start[1]; // vertical (world +y ≈ downward, so up = negative)
  const dz = end[2] - start[2]; // depth (forward)
  const absDx = Math.abs(dx);
  const absDy = Math.abs(dy);
  const absDz = Math.abs(dz);

  // 1. Uppercut: dominant vertical motion AND it's upward (dy < 0).
  if (absDy >= UPPERCUT_VERTICAL_RATIO * Math.max(absDx, absDz, 1e-6) && dy < 0) return "uppercut";
  // 2. Hook: lateral motion dominates forward.
  if (absDx >= HOOK_LATERAL_RATIO * Math.max(absDz, 1e-6)) return "hook";
  // 3. Straight punch — jab if lead hand, cross if rear; default jab when no stance.
  const s = stance ? stance.toLowerCase() : null;
  const isLead = (s === "orthodox" && hand === "left") || (s === "southpaw" && hand === "right");
  if (s === "orthodox" || s === "southpaw") return isLead ? "jab" : "cross";
  return "jab";
}

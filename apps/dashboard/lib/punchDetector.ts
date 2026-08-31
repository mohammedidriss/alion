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

// MediaPipe landmark indices
const LM_LEFT_SHOULDER = 11;
const LM_RIGHT_SHOULDER = 12;
const LM_LEFT_WRIST = 15;
const LM_RIGHT_WRIST = 16;

// Defaults mirror the Python reference (validated on real sessions). The key
// discriminator is ballistic peak velocity; the excursion cycle makes it one
// count per punch and requires real out-and-back travel.
const MIN_PEAK_VELOCITY_MS = 2.5; // was 1.2 (far too low); 3.0 under-caught depth-axis punches
const MIN_EXCURSION_M = 0.04; // min wrist travel valley→peak, metres (world coords)
const HYSTERESIS_M = 0.03; // turn-around must exceed this to confirm a peak/valley
const REFRACTORY_MS = 250;
const MIN_VISIBILITY = 0.5;
const LEGACY_BODY_WIDTH = 0.45; // 2D-fallback scale (no world landmarks)

export type Hand = "left" | "right";

export interface PunchEvent {
  t_ms: number;
  hand: Hand;
  velocity_ms: number;
  confidence: number;
  detected_by: string;
  lead_or_rear: "lead" | "rear" | null;
  velocity_source: string;
}

type Vec3 = [number, number, number];

interface Landmark {
  x: number;
  y: number;
  z: number;
  visibility?: number;
}

/** Hysteresis peak/valley tracker over the wrist→shoulder extension signal. */
interface HandCycle {
  goingUp: boolean;
  extreme: number | null; // current local extreme (peak while up, valley while down)
  chamber: number | null; // last confirmed valley — the excursion baseline
  risePeakSpeed: number;
  peakT: number;
  lastPos: Vec3 | null;
  lastT: number | null;
  lastEventT: number | null;
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
  };
}

function dist(a: Vec3, b: Vec3): number {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
}

function getLandmark(lms: Landmark[], idx: number): Landmark | null {
  const lm = lms[idx];
  if (!lm || (lm.visibility ?? 1) < MIN_VISIBILITY) return null;
  return lm;
}

function handToLeadRear(hand: Hand, stance: string | null): "lead" | "rear" | null {
  if (stance === "orthodox") return hand === "left" ? "lead" : "rear";
  if (stance === "southpaw") return hand === "right" ? "lead" : "rear";
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

  constructor(stance: string | null = null) {
    this.stance = stance;
  }

  reset() {
    this.left = makeHandCycle();
    this.right = makeHandCycle();
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

    const events: PunchEvent[] = [];
    const el = this.step(lms, "left", LM_LEFT_WRIST, LM_LEFT_SHOULDER, this.left, tMs, useWorld);
    if (el) events.push(el);
    const er = this.step(lms, "right", LM_RIGHT_WRIST, LM_RIGHT_SHOULDER, this.right, tMs, useWorld);
    if (er) events.push(er);
    return events;
  }

  private step(
    lms: Landmark[],
    hand: Hand,
    wristIdx: number,
    shoulderIdx: number,
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
    if (cyc.lastPos && cyc.lastT !== null) {
      const dtS = Math.max(1e-3, (tMs - cyc.lastT) / 1000);
      speed = (dist(wrist, cyc.lastPos) * scale) / dtS;
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

    return ev;
  }
}

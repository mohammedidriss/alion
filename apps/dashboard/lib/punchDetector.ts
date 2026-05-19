/**
 * Client-side punch detector — TypeScript port of packages/analyze/punch_detector_heuristic.py
 *
 * Uses MediaPipe PoseLandmarker world landmarks (3-D, metric, hip-centred) when
 * available, falls back to normalised image-plane landmarks.
 *
 * All thresholds are tuned to match the Python reference.
 */

// MediaPipe landmark indices
const LM_LEFT_SHOULDER = 11;
const LM_RIGHT_SHOULDER = 12;
const LM_LEFT_ELBOW = 13;
const LM_RIGHT_ELBOW = 14;
const LM_LEFT_WRIST = 15;
const LM_RIGHT_WRIST = 16;
const LM_LEFT_HIP = 23;
const LM_RIGHT_HIP = 24;

const THRESHOLD_MS = 1.2;
const LEGACY_THRESHOLD_MS = 0.5;
const REFRACTORY_MS = 150;
const BODY_MOTION_THRESHOLD_MS = 2.0;
const MIN_FORWARD_TRAVEL = 0.015;
const MIN_ELBOW_ANGLE_DEG = 60;
const MIN_EXTENSION_RATIO = 1.02;
const CHAMBERED_MAX_DEG = 110;
const EXTENDED_MIN_DEG = 150;
const PUNCH_WINDOW_MS = 600;
const REST_WINDOW_S = 2.0;
const REST_BODY_SPEED_MS = 0.05;
const REST_THRESHOLD_FACTOR = 1.8;
const DECEL_FACTOR = 0.97;
const MIN_VISIBILITY = 0.5;
const LEGACY_BODY_WIDTH = 0.45;

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

interface HandState {
  lastPos: Vec3 | null;
  lastT: number | null;
  lastSpeed: number;
  lastEventT: number | null;
  posHistory: Vec3[];
  extensionHistory: number[];
  lastChamberedT: number | null;
}

interface BodyState {
  lastHipPos: Vec3 | null;
  lastT: number | null;
  speedMs: number;
  speedHistory: number[];
}

function makeHandState(): HandState {
  return { lastPos: null, lastT: null, lastSpeed: 0, lastEventT: null, posHistory: [], extensionHistory: [], lastChamberedT: null };
}

function makeBodyState(): BodyState {
  return { lastHipPos: null, lastT: null, speedMs: 0, speedHistory: [] };
}

function dist(a: Vec3, b: Vec3): number {
  return Math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2);
}

function elbowAngleDeg(shoulder: Vec3, elbow: Vec3, wrist: Vec3): number {
  const ux = shoulder[0] - elbow[0], uy = shoulder[1] - elbow[1], uz = shoulder[2] - elbow[2];
  const vx = wrist[0] - elbow[0], vy = wrist[1] - elbow[1], vz = wrist[2] - elbow[2];
  const nu = Math.sqrt(ux * ux + uy * uy + uz * uz);
  const nv = Math.sqrt(vx * vx + vy * vy + vz * vz);
  if (nu < 1e-6 || nv < 1e-6) return 0;
  const cosA = Math.max(-1, Math.min(1, (ux * vx + uy * vy + uz * vz) / (nu * nv)));
  return (Math.acos(cosA) * 180) / Math.PI;
}

function getLandmark(lms: Landmark[], idx: number): Landmark | null {
  const lm = lms[idx];
  if (!lm || (lm.visibility ?? 1) < MIN_VISIBILITY) return null;
  return lm;
}

function hipCenter(lms: Landmark[]): Vec3 | null {
  const l = getLandmark(lms, LM_LEFT_HIP);
  const r = getLandmark(lms, LM_RIGHT_HIP);
  if (!l || !r) return null;
  return [(l.x + r.x) / 2, (l.y + r.y) / 2, (l.z + r.z) / 2];
}

function handToLeadRear(hand: Hand, stance: string | null): "lead" | "rear" | null {
  if (stance === "orthodox") return hand === "left" ? "lead" : "rear";
  if (stance === "southpaw") return hand === "right" ? "lead" : "rear";
  return null;
}

export class PunchDetector {
  private stance: string | null;
  private left = makeHandState();
  private right = makeHandState();
  private body = makeBodyState();

  constructor(stance: string | null = null) {
    this.stance = stance;
  }

  reset() {
    this.left = makeHandState();
    this.right = makeHandState();
    this.body = makeBodyState();
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

    this.updateBody(lms, tMs, useWorld);

    const events: PunchEvent[] = [];
    const el = this.step(lms, "left", LM_LEFT_WRIST, LM_LEFT_SHOULDER, LM_LEFT_ELBOW, this.left, tMs, useWorld);
    if (el) events.push(el);
    const er = this.step(lms, "right", LM_RIGHT_WRIST, LM_RIGHT_SHOULDER, LM_RIGHT_ELBOW, this.right, tMs, useWorld);
    if (er) events.push(er);
    return events;
  }

  private updateBody(lms: Landmark[], tMs: number, useWorld: boolean) {
    const hip = hipCenter(lms);
    if (!hip) { this.body.lastHipPos = null; this.body.lastT = null; this.body.speedMs = 0; return; }
    if (this.body.lastHipPos && this.body.lastT !== null) {
      const dtS = Math.max(1e-3, (tMs - this.body.lastT) / 1000);
      let d = dist(hip, this.body.lastHipPos);
      if (!useWorld) d *= LEGACY_BODY_WIDTH;
      this.body.speedMs = d / dtS;
      this.body.speedHistory.push(this.body.speedMs);
      if (this.body.speedHistory.length > 120) this.body.speedHistory.shift();
    }
    this.body.lastHipPos = hip;
    this.body.lastT = tMs;
  }

  private isAtRest(): boolean {
    const hist = this.body.speedHistory;
    if (hist.length < 60) return false;
    const recent = hist.slice(-60);
    return Math.max(...recent) < REST_BODY_SPEED_MS;
  }

  private step(
    lms: Landmark[], hand: Hand,
    wristIdx: number, shoulderIdx: number, elbowIdx: number,
    st: HandState, tMs: number, useWorld: boolean,
  ): PunchEvent | null {
    const wristLm = getLandmark(lms, wristIdx);
    const shLm = getLandmark(lms, shoulderIdx);
    const elLm = getLandmark(lms, elbowIdx);
    if (!wristLm || !shLm) { this.resetHand(st); return null; }

    const wrist: Vec3 = [wristLm.x, wristLm.y, wristLm.z];
    const shoulder: Vec3 = [shLm.x, shLm.y, shLm.z];
    const elbow: Vec3 = elLm ? [elLm.x, elLm.y, elLm.z] : shoulder;
    const elbowOk = !!elLm;
    const elbowAngle = elbowOk ? elbowAngleDeg(shoulder, elbow, wrist) : 180;
    const extension = dist(wrist, shoulder);

    let ev: PunchEvent | null = null;

    if (st.lastPos && st.lastT !== null) {
      const dtS = Math.max(1e-3, (tMs - st.lastT) / 1000);
      let d = dist(wrist, st.lastPos);
      if (!useWorld) d *= LEGACY_BODY_WIDTH;
      const speed = d / dtS;

      const baseThreshold = useWorld ? THRESHOLD_MS : LEGACY_THRESHOLD_MS;
      const atRest = this.isAtRest();

      const crossedThreshold = st.lastSpeed >= baseThreshold;
      const decelerating = speed < st.lastSpeed * DECEL_FACTOR;
      const spaced = st.lastEventT === null || (tMs - st.lastEventT) >= REFRACTORY_MS;

      if (crossedThreshold && decelerating && spaced) {
        const baseConf = Math.max(0.1, Math.min(1, (st.lastSpeed - baseThreshold) / Math.max(baseThreshold, 1e-3)));
        let softPenalty = 1.0;
        if (atRest) softPenalty *= 0.5;
        if (this.body.speedMs >= BODY_MOTION_THRESHOLD_MS) softPenalty *= 0.7;
        if (!this.hasForwardExtended(st, extension)) softPenalty *= 0.8;
        if (elbowAngle > 0 && elbowAngle < MIN_ELBOW_ANGLE_DEG) softPenalty *= 0.8;
        if (!this.extensionRatioOk(st, extension)) softPenalty *= 0.8;
        if (elbowAngle >= EXTENDED_MIN_DEG) {
          const chamberedRecently = st.lastChamberedT !== null && (tMs - st.lastChamberedT) <= PUNCH_WINDOW_MS;
          if (!chamberedRecently) softPenalty *= 0.8;
        }
        const visibilityFactor = Math.min(shLm.visibility ?? 1, wristLm.visibility ?? 1);
        const conf = Math.max(0.05, baseConf * softPenalty * visibilityFactor);

        ev = {
          t_ms: tMs,
          hand,
          velocity_ms: Math.round(st.lastSpeed * 100) / 100,
          confidence: Math.round(conf * 100) / 100,
          detected_by: "heuristic",
          lead_or_rear: handToLeadRear(hand, this.stance),
          velocity_source: useWorld ? "world" : "image_heuristic",
        };
        st.lastEventT = tMs;
      }
      st.lastSpeed = speed;
    }

    st.lastPos = wrist;
    st.lastT = tMs;
    st.extensionHistory.push(extension);
    if (st.extensionHistory.length > 10) st.extensionHistory.shift();
    if (elbowOk && elbowAngle > 1 && elbowAngle <= CHAMBERED_MAX_DEG) st.lastChamberedT = tMs;

    return ev;
  }

  private extensionRatioOk(st: HandState, currentExt: number): boolean {
    if (st.extensionHistory.length < 4) return false;
    const windowMin = Math.min(...st.extensionHistory.slice(-10));
    if (windowMin < 1e-6) return currentExt > 0.05;
    return currentExt / windowMin >= MIN_EXTENSION_RATIO;
  }

  private hasForwardExtended(st: HandState, currentExt: number): boolean {
    if (st.extensionHistory.length < 3) return false;
    const recent = st.extensionHistory.slice(-5);
    const recentMin = Math.min(...recent);
    return (currentExt - recentMin) >= MIN_FORWARD_TRAVEL;
  }

  private resetHand(st: HandState) {
    st.lastPos = null; st.lastT = null; st.lastSpeed = 0;
  }
}

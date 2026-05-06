const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Stance = "orthodox" | "southpaw" | "switch";
export type SessionSource =
  | "live_webcam"
  | "uploaded_video"
  | "live_iphone"
  | "polar_h10_only"
  | "hrv_replay";
export type SessionStatus =
  | "pending"
  | "capturing"
  | "processing"
  | "completed"
  | "failed";
export type Hand = "left" | "right";
export type LeadOrRear = "lead" | "rear";
export type PunchType = "jab" | "cross" | "hook" | "uppercut";
export type DetectionSource = "heuristic" | "lstm_v1";
export type VelocitySource = "world" | "image_heuristic";
export type SkillLevel =
  | "recreational"
  | "amateur_novice"
  | "amateur_open"
  | "amateur_elite"
  | "semi_pro"
  | "professional"
  | "coach";

export interface Fighter {
  id: string;
  name: string;
  nickname: string | null;
  dob: string | null;
  nationality: string | null;
  sex: string | null;
  stance: Stance;
  dominant_hand: Hand | null;
  height_cm: number | null;
  reach_cm: number | null;
  weight_kg: number | null;
  shoulder_width_cm: number | null;
  skill_level: SkillLevel | null;
  weight_class: string | null;
  years_training: number | null;
  gym: string | null;
  trainer: string | null;
  record_wins: number;
  record_losses: number;
  record_draws: number;
  record_kos: number;
  boxrec_id: string | null;
  usa_boxing_id: string | null;
  notes: string | null;
  created_at: string;
}

export type FighterPatch = Partial<Omit<Fighter, "id" | "created_at">>;

export interface WeighIn {
  id: number;
  fighter_id: string;
  weight_kg: number;
  recorded_at: string;
  notes: string | null;
}

export interface FighterOptions {
  stances: string[];
  hands: string[];
  skill_levels: string[];
  weight_classes: string[];
  sexes: string[];
}

// ---- HRV (Phase 2 / v2) ----

export interface HRSample {
  session_id: string;
  t_ms: number;
  rr_ms: number;
  hr_bpm: number;
}

export interface HRMetricsWindow {
  session_id: string;
  window_start_ms: number;
  window_end_ms: number;
  sample_count: number;
  mean_hr_bpm: number;
  rmssd_ms: number;
  sdnn_ms: number;
}

export interface HrvStatus {
  session_id: string;
  is_running: boolean;
  sample_count: number;
  metrics: HRMetricsWindow | null;
}

export interface Session {
  id: string;
  fighter_id: string;
  source: SessionSource;
  status: SessionStatus;
  started_at: string;
  ended_at: string | null;
  video_path: string | null;
  pose_parquet_path: string | null;
  frame_count: number;
  duration_ms: number;
  notes: string | null;
  failure_reason: string | null;
  baseline_rmssd_ms: number | null;
  baseline_sdnn_ms: number | null;
  baseline_mean_hr_bpm: number | null;
  baseline_recorded_at: string | null;
}

export interface PerformanceScore {
  session_id: string;
  peak_velocity_p90: number;
  ppm: number;
  duration_min: number;
  score: number;
  punch_count: number;
  baseline_rmssd_ms: number | null;
  baseline_sdnn_ms: number | null;
  baseline_mean_hr_bpm: number | null;
}

export interface MatrixPoint {
  session_id: string;
  started_at: string;
  baseline_rmssd_ms: number;
  baseline_sdnn_ms: number | null;
  baseline_mean_hr_bpm: number | null;
  peak_velocity_p90: number;
  ppm: number;
  duration_min: number;
  score: number;
  punch_count: number;
}

export interface MatrixResponse {
  fighter_id: string;
  points: MatrixPoint[];
  pearson_r: number | null;
  slope: number | null;
  intercept: number | null;
}

export interface Capabilities {
  cv_available: boolean;
  cv_reason: string | null;
  webcam_likely: boolean;
}

export interface PunchEvent {
  session_id: string;
  t_ms: number;
  hand: Hand;
  lead_or_rear: LeadOrRear | null;
  velocity_ms: number;
  velocity_source: VelocitySource;
  punch_type: PunchType | null;
  detected_by: DetectionSource;
  confidence: number;
}

export interface Camera {
  index: number;
  width: number;
  height: number;
  fps: number;
}

export interface CamerasResponse {
  cameras: Camera[];
  cv_available: boolean;
  reason: string | null;
}

export interface CaptureStatus {
  session_id: string;
  status: SessionStatus;
  is_running: boolean;
  is_paused?: boolean;
  frame_count: number;
  duration_ms: number;
  punch_count: number;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}

export const api = {
  capabilities: () => req<Capabilities>("/health/capabilities"),
  listFighters: () => req<Fighter[]>("/fighters"),
  getFighter: (id: string) => req<Fighter>(`/fighters/${id}`),
  createFighter: (name: string, stance: Stance = "orthodox") =>
    req<Fighter>("/fighters", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, stance }),
    }),
  updateFighter: (id: string, patch: FighterPatch) =>
    req<Fighter>(`/fighters/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteFighter: (id: string) =>
    req<void>(`/fighters/${id}`, { method: "DELETE" }),
  fighterOptions: () => req<FighterOptions>("/fighters/options"),
  listWeighIns: (id: string) => req<WeighIn[]>(`/fighters/${id}/weigh-ins`),
  createWeighIn: (id: string, weight_kg: number, notes?: string) =>
    req<WeighIn>(`/fighters/${id}/weigh-ins`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ weight_kg, notes }),
    }),
  deleteWeighIn: (fighter_id: string, weigh_in_id: number) =>
    req<void>(`/fighters/${fighter_id}/weigh-ins/${weigh_in_id}`, {
      method: "DELETE",
    }),
  // HRV (Phase 2, /v2)
  uploadHrvCsv: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/v2/sessions/${id}/hrv/upload`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Session>;
  },
  startHrv: (id: string, opts?: { realtime?: boolean }) =>
    req<HrvStatus>(`/v2/sessions/${id}/hrv/start`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ realtime: opts?.realtime ?? false }),
    }),
  stopHrv: (id: string) =>
    req<HrvStatus>(`/v2/sessions/${id}/hrv/stop`, { method: "POST" }),
  hrvStatus: (id: string) => req<HrvStatus>(`/v2/sessions/${id}/hrv/status`),
  hrvSamples: (id: string, limit?: number) =>
    req<HRSample[]>(
      `/v2/sessions/${id}/hrv/samples${limit ? `?limit=${limit}` : ""}`,
    ),
  listSessions: (fighter_id?: string) =>
    req<Session[]>(
      fighter_id ? `/sessions?fighter_id=${fighter_id}` : "/sessions",
    ),
  getSession: (id: string) => req<Session>(`/sessions/${id}`),
  createSession: (fighter_id: string, source: SessionSource) =>
    req<Session>("/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fighter_id, source }),
    }),
  deleteSession: (id: string) =>
    req<void>(`/sessions/${id}`, { method: "DELETE" }),
  uploadVideo: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/sessions/${id}/upload`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Session>;
  },
  startCapture: (
    id: string,
    opts?: { max_frames?: number; camera_index?: number },
  ) =>
    req<CaptureStatus>(`/sessions/${id}/capture/start`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        max_frames: opts?.max_frames,
        camera_index: opts?.camera_index ?? 0,
      }),
    }),
  listCameras: () => req<CamerasResponse>("/cameras"),
  stopCapture: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/stop`, { method: "POST" }),
  pauseCapture: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/pause`, { method: "POST" }),
  resumeCapture: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/resume`, { method: "POST" }),
  reprocessCapture: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/reprocess`, { method: "POST" }),
  annotateSession: (id: string, notes: string | null) =>
    req<Session>(`/sessions/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ notes }),
    }),
  eventsCsvUrl: (id: string) => `${BASE}/sessions/${id}/events.csv`,
  captureStatus: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/status`),
  listEvents: (id: string) => req<PunchEvent[]>(`/sessions/${id}/events`),
  uploadBaseline: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/sessions/${id}/baseline/upload`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Session>;
  },
  sessionPerformance: (id: string) =>
    req<PerformanceScore>(`/sessions/${id}/performance`),
  fighterMatrix: (id: string) =>
    req<MatrixResponse>(`/fighters/${id}/matrix`),
};

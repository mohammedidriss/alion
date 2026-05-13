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
export type DetectionSource = "heuristic" | "lstm_v1" | "custom_ml";
export type VelocitySource = "world" | "image_heuristic";
export type PoseBackend = "mediapipe" | "yolov8";
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
  gym_id: string | null;
  trainer: string | null;
  record_wins: number;
  record_losses: number;
  record_draws: number;
  record_kos: number;
  boxrec_id: string | null;
  usa_boxing_id: string | null;
  notes: string | null;
  photo_path: string | null;
  bio: string | null;
  career_history: string | null;
  created_at: string;
}

export type FighterPatch = Partial<Omit<Fighter, "id" | "created_at">>;

// ---- Team: titles / sponsors / coach assignments ----

export type TitleStatus = "active" | "lost" | "vacated" | "retired";

export interface FighterTitle {
  id: number;
  fighter_id: string;
  name: string;
  organization: string | null;
  weight_class: string | null;
  won_on: string | null;
  lost_on: string | null;
  status: TitleStatus;
  notes: string | null;
  created_at: string;
}

export interface FighterSponsor {
  id: number;
  fighter_id: string;
  name: string;
  started_on: string | null;
  ended_on: string | null;
  website: string | null;
  notes: string | null;
  created_at: string;
}

export type CoachRole =
  | "head_coach"
  | "striking"
  | "strength"
  | "conditioning"
  | "nutrition"
  | "cutman"
  | "mental"
  | "other";

export interface CoachAssignment {
  id: number;
  fighter_id: string;
  coach_id: string;
  coach_name: string;
  coach_photo_path: string | null;
  role: CoachRole;
  started_on: string | null;
  ended_on: string | null;
  notes: string | null;
  created_at: string;
}

export type CoachingLevel = "amateur" | "professional" | "both";

export interface Coach {
  id: string;
  name: string;
  photo_path: string | null;
  dob: string | null;
  nationality: string | null;
  sex: string | null;
  email: string | null;
  phone: string | null;
  gym: string | null;
  gym_id: string | null;
  specialties: string | null;
  coaching_level: CoachingLevel | null;
  years_experience: number | null;
  certifications: string | null;
  license_number: string | null;
  license_expiry: string | null;
  languages: string | null;
  notable_fighters: string | null;
  bio: string | null;
  notes: string | null;
  created_at: string;
}

export type CoachPatch = Partial<Omit<Coach, "id" | "created_at">>;

export interface CoachNote {
  id: number;
  coach_id: string;
  fighter_id: string;
  coach_name: string;
  coach_photo_path: string | null;
  content: string;
  created_at: string;
}

export interface Gym {
  id: string;
  name: string;
  address: string | null;
  city: string | null;
  country: string | null;
  phone: string | null;
  email: string | null;
  specialties: string | null;
  notes: string | null;
  created_at: string;
}

export type GymPatch = Partial<Omit<Gym, "id" | "created_at">>;

export interface GymMembership {
  id: number;
  gym_id: string;
  member_id: string;
  member_type: "fighter" | "coach";
  member_name: string;
  joined_on: string | null;
  left_on: string | null;
  created_at: string;
}

export interface GymManager {
  id: string;
  name: string;
  photo_path: string | null;
  email: string | null;
  phone: string | null;
  gym_id: string;
  gym_name: string;
  notes: string | null;
  created_at: string;
}

export type GymManagerPatch = Partial<Pick<GymManager, "name" | "email" | "phone" | "notes">>;

export type RefereeCertLevel = "local" | "regional" | "national" | "international";

export interface Referee {
  id: string;
  name: string;
  photo_path: string | null;
  dob: string | null;
  nationality: string | null;
  sex: string | null;
  email: string | null;
  phone: string | null;
  license_number: string | null;
  sanctioning_body: string | null;
  certification_level: RefereeCertLevel | null;
  license_expiry: string | null;
  years_officiating: number | null;
  languages: string | null;
  notable_bouts: string | null;
  bio: string | null;
  notes: string | null;
  created_at: string;
}

export type RefereePatch = Partial<Omit<Referee, "id" | "created_at">>;

export type AllergySeverity = "mild" | "moderate" | "severe" | "anaphylactic";
export type ConditionStatus = "active" | "managed" | "recovered";

export interface MedicalRecord {
  fighter_id: string;
  blood_type: string | null;
  last_clearance_date: string | null;
  clearing_physician: string | null;
  primary_physician: string | null;
  primary_physician_phone: string | null;
  emergency_contact_name: string | null;
  emergency_contact_relation: string | null;
  emergency_contact_phone: string | null;
  insurance_provider: string | null;
  insurance_policy: string | null;
  notes: string | null;
  updated_at: string;
}

export type MedicalRecordPatch = Partial<
  Omit<MedicalRecord, "fighter_id" | "updated_at">
>;

export interface Allergy {
  id: number;
  fighter_id: string;
  substance: string;
  severity: AllergySeverity;
  notes: string | null;
  created_at: string;
}

export interface Medication {
  id: number;
  fighter_id: string;
  name: string;
  dose: string | null;
  frequency: string | null;
  started_on: string | null;
  prescribed_by: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
}

export interface MedicalCondition {
  id: number;
  fighter_id: string;
  name: string;
  diagnosed_on: string | null;
  status: ConditionStatus;
  notes: string | null;
  created_at: string;
}

export interface WeighIn {
  id: number;
  fighter_id: string;
  weight_kg: number;
  recorded_at: string;
  notes: string | null;
}

export interface WeightAnalysis {
  total_entries: number;
  current_kg: number | null;
  min_kg: number | null;
  max_kg: number | null;
  range_kg: number | null;
  mean_kg: number | null;
  std_kg: number | null;
  cv_pct: number | null;
  trend_direction: string | null;
  trend_kg_per_week: number | null;
  instability_flag: boolean;
  ai_summary: string;
  ai_recommendations: string[];
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
  round_count: number | null;
  round_duration_s: number | null;
  rest_duration_s: number | null;
  pose_backend: PoseBackend;
}

export type AttachmentKind = "video" | "image" | "audio" | "document" | "other";

export interface SessionAttachment {
  id: number;
  session_id: string;
  filename: string;
  path: string;
  mime_type: string | null;
  size_bytes: number;
  kind: AttachmentKind;
  notes: string | null;
  uploaded_at: string;
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
  trimp_score: number | null;
}

export interface CoachAdviceResponse {
  summary: string;
  action_items: string[];
}

export interface FighterObservationResponse {
  observations: string[];
  strengths: string[];
  weaknesses: string[];
  training_plan: string[];
  summary: string;
}

export interface PerformanceTrendItem {
  date: string;
  punch_count: number;
  peak_velocity_ms: number;
  ppm: number;
  score: number;
  duration_min: number;
  baseline_rmssd_ms: number | null;
}

export interface PerformanceTrendResponse {
  months: number;
  sessions_count: number;
  items: PerformanceTrendItem[];
}

export interface RoundPlan {
  id: number;
  name: string;
  round_count: number;
  round_duration_s: number;
  rest_duration_s: number;
  created_at: string;
}

export interface RoundPlanCreate {
  name: string;
  round_count: number;
  round_duration_s: number;
  rest_duration_s: number;
}

export const MAX_ROUND_PLANS = 3;

export interface ReprocessResponse {
  session_id: string;
  second_pass_name: string;
  live_count: number;
  offline_count: number;
  consensus_count: number;
  live_only: number;
  offline_only: number;
}

export type ConsensusKind = "consensus" | "live_only" | "offline_only";

export interface ConsensusEvent {
  t_ms: number;
  hand: "left" | "right";
  velocity_ms: number;
  punch_type: string | null;
  confidence: number;
  kind: ConsensusKind;
  sources: string;
  second_pass_name: string;
}

export interface RQ1Rating {
  session_id: string;
  payload_mode: PayloadMode;
  rater_id: string;
  criterion: string;
  score: number;
  notes: string | null;
  created_at: string;
}

export interface RQ1RatingUpsert {
  payload_mode: PayloadMode;
  rater_id: string;
  criterion: string;
  score: number;
  notes?: string | null;
}

export type PayloadMode = "cv" | "hrv" | "imu" | "fused";

export interface IMUSample {
  session_id: string;
  t_ms: number;
  ax_g: number;
  ay_g: number;
  az_g: number;
  gx_dps: number;
  gy_dps: number;
  gz_dps: number;
  hand: "left" | "right" | null;
}

export interface RoundCvBlock {
  punch_count: number;
  peak_velocity_ms: number | null;
  ppm: number | null;
}
export interface RoundHrvBlock {
  sample_count: number;
  mean_hr_bpm: number | null;
  peak_hr_bpm: number | null;
  rmssd_ms: number | null;
  rmssd_delta_vs_baseline_ms: number | null;
}
export interface RoundImuBlock {
  sample_count: number;
  peak_g: number | null;
  n_impacts: number;
  cv_imu_match_rate: number | null;
}

export interface RoundExportItem {
  round_number: number;
  start_ms: number;
  end_ms: number;
  duration_ms: number;
  rest_after_ms: number;
  punch_count: number;
  peak_velocity_ms: number | null;
  ppm: number | null;
  cv: RoundCvBlock;
  hrv: RoundHrvBlock;
  imu: RoundImuBlock;
}

export interface RoundsExportResponse {
  session_id: string;
  fighter_id: string;
  started_at: string;
  round_count: number;
  round_duration_s: number;
  rest_duration_s: number;
  rounds: RoundExportItem[];
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
  /** Hopkins' Smallest Worthwhile Change (0.2 × stdev of session scores).
   *  Use to threshold the "vs previous" delta: |delta| > swc means a real
   *  change, not noise. None when n < 3. */
  swc: number | null;
}

export type ReadinessMode = "z_score" | "absolute";

export interface FighterReadiness {
  fighter_id: string;
  score: number;
  mode: ReadinessMode;
  rmssd_ms: number | null;
  history_n: number;
  baseline_mean_ms: number | null;
  baseline_sd_ms: number | null;
  z: number | null;
  min_history_required: number;
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

export type UserRole = "fighter" | "coach" | "referee" | "gym_manager" | "admin";

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  role: UserRole;
  profile_id: string | null;
  photo_path: string | null;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  // Auto-attach auth token from storage
  const token =
    (typeof window !== "undefined" &&
      (localStorage.getItem("alion.token") ??
        sessionStorage.getItem("alion.token"))) ||
    null;
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string>),
  };
  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const r = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
    headers,
  });
  if (r.status === 401 && typeof window !== "undefined") {
    // Token expired or invalid — clear auth and redirect to login
    localStorage.removeItem("alion.token");
    sessionStorage.removeItem("alion.token");
    window.location.href = "/";
    throw new Error("Session expired. Please sign in again.");
  }
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  if (r.status === 204) return undefined as T;
  return r.json();
}

export const api = {
  capabilities: () => req<Capabilities>("/health/capabilities"),
  listFighters: (gymId?: string) =>
    req<Fighter[]>(gymId ? `/fighters?gym_id=${gymId}` : "/fighters"),
  getFighter: (id: string) => req<Fighter>(`/fighters/${id}`),
  generateObservations: (fighterId: string) =>
    req<FighterObservationResponse>(
      `/fighters/${fighterId}/observations/generate`,
      { method: "POST" },
    ),
  performanceTrend: (fighterId: string, months: number = 3) =>
    req<PerformanceTrendResponse>(
      `/fighters/${fighterId}/performance-trend?months=${months}`,
    ),
  createFighter: (name: string, stance: Stance = "orthodox", gymId?: string) =>
    req<Fighter>("/fighters", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, stance, ...(gymId ? { gym_id: gymId } : {}) }),
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
  weightAnalysis: (id: string) => req<WeightAnalysis>(`/fighters/${id}/weight-analysis`),
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
  createSession: (fighter_id: string, source: SessionSource, pose_backend: PoseBackend = "mediapipe") =>
    req<Session>("/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fighter_id, source, pose_backend }),
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
    opts?: { max_frames?: number; camera_index?: number; pose_backend?: PoseBackend },
  ) =>
    req<CaptureStatus>(`/sessions/${id}/capture/start`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        max_frames: opts?.max_frames,
        camera_index: opts?.camera_index ?? 0,
        pose_backend: opts?.pose_backend ?? "mediapipe",
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
  patchSessionConfig: (
    id: string,
    config: {
      round_count?: number | null;
      round_duration_s?: number | null;
      rest_duration_s?: number | null;
    },
  ) =>
    req<Session>(`/sessions/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(config),
    }),
  listAttachments: (id: string) =>
    req<SessionAttachment[]>(`/sessions/${id}/attachments`),
  uploadAttachment: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/sessions/${id}/attachments`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<SessionAttachment>;
  },
  deleteAttachment: (id: string, attachmentId: number) =>
    req<void>(`/sessions/${id}/attachments/${attachmentId}`, {
      method: "DELETE",
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
  generateAdvice: (id: string, payload_mode: PayloadMode = "fused") =>
    req<CoachAdviceResponse>(
      `/sessions/${id}/advice?payload_mode=${payload_mode}`,
      { method: "POST" },
    ),
  roundsExport: (id: string) =>
    req<RoundsExportResponse>(`/sessions/${id}/rounds_export`),
  imuSamples: (id: string) => req<IMUSample[]>(`/sessions/${id}/imu/samples`),

  // Saved round-structure plans (cap of 3 enforced server-side).
  listRoundPlans: () => req<RoundPlan[]>(`/round_plans`),
  createRoundPlan: (data: RoundPlanCreate) =>
    req<RoundPlan>(`/round_plans`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateRoundPlan: (id: number, data: Partial<RoundPlanCreate>) =>
    req<RoundPlan>(`/round_plans/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteRoundPlan: (id: number) =>
    req<void>(`/round_plans/${id}`, { method: "DELETE" }),

  // Offline reconciliation (live heuristic + LSTM second pass).
  reprocessOffline: (id: string) =>
    req<ReprocessResponse>(`/sessions/${id}/reprocess_offline`, {
      method: "POST",
    }),
  listConsensusEvents: (id: string) =>
    req<ConsensusEvent[]>(`/sessions/${id}/consensus_events`),
  synthesizeIMU: (id: string) =>
    req<number>(`/sessions/${id}/imu/synth`, { method: "POST" }),
  loadHrvSync: (id: string) =>
    req<number>(`/v2/sessions/${id}/hrv/load`, { method: "POST" }),

  // ---- RQ1 study ----
  rq1ListRatings: (sessionId: string, raterId?: string) =>
    req<RQ1Rating[]>(
      `/studies/rq1/sessions/${sessionId}/ratings${
        raterId ? `?rater_id=${encodeURIComponent(raterId)}` : ""
      }`,
    ),
  rq1UpsertRating: (sessionId: string, body: RQ1RatingUpsert) =>
    req<RQ1Rating>(`/studies/rq1/sessions/${sessionId}/ratings`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    }),
  fighterMatrix: (id: string) =>
    req<MatrixResponse>(`/fighters/${id}/matrix`),
  fighterReadiness: (id: string) =>
    req<FighterReadiness | null>(`/fighters/${id}/readiness`),

  // ---- Coaches ----
  listCoaches: (gymId?: string) =>
    req<Coach[]>(gymId ? `/coaches?gym_id=${gymId}` : "/coaches"),
  getCoach: (id: string) => req<Coach>(`/coaches/${id}`),
  createCoach: (data: { name: string; gym?: string; gym_id?: string }) =>
    req<Coach>("/coaches", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateCoach: (id: string, patch: CoachPatch) =>
    req<Coach>(`/coaches/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteCoach: (id: string) =>
    req<void>(`/coaches/${id}`, { method: "DELETE" }),
  uploadCoachPhoto: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const token =
      (typeof window !== "undefined" &&
        (localStorage.getItem("alion.token") ??
          sessionStorage.getItem("alion.token"))) ||
      null;
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const r = await fetch(`${BASE}/coaches/${id}/photo`, {
      method: "POST",
      body: fd,
      headers,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Coach>;
  },
  listCoachFighters: (coachId: string) =>
    req<Fighter[]>(`/coaches/${coachId}/fighters`),
  createCoachNote: (coachId: string, fighterId: string, content: string) =>
    req<CoachNote>(`/coaches/${coachId}/fighters/${fighterId}/notes`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ content }),
    }),
  listCoachNotes: (coachId: string) =>
    req<CoachNote[]>(`/coaches/${coachId}/notes`),
  deleteCoachNote: (coachId: string, noteId: number) =>
    req<void>(`/coaches/${coachId}/notes/${noteId}`, { method: "DELETE" }),
  listFighterCoachNotes: (fighterId: string) =>
    req<CoachNote[]>(`/fighters/${fighterId}/coach-notes`),

  // ---- Referees ----
  listReferees: () => req<Referee[]>("/referees"),
  getReferee: (id: string) => req<Referee>(`/referees/${id}`),
  createReferee: (data: { name: string; sanctioning_body?: string }) =>
    req<Referee>("/referees", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateReferee: (id: string, patch: RefereePatch) =>
    req<Referee>(`/referees/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteReferee: (id: string) =>
    req<void>(`/referees/${id}`, { method: "DELETE" }),
  uploadRefereePhoto: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/referees/${id}/photo`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Referee>;
  },

  // ---- Gyms ----
  listGyms: () => req<Gym[]>("/gyms"),
  getGym: (id: string) => req<Gym>(`/gyms/${id}`),
  createGym: (data: { name: string; address?: string; city?: string; country?: string; phone?: string; email?: string; specialties?: string }) =>
    req<Gym>("/gyms", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateGym: (id: string, patch: GymPatch) =>
    req<Gym>(`/gyms/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteGym: (id: string) =>
    req<void>(`/gyms/${id}`, { method: "DELETE" }),
  listGymMembers: (gymId: string) =>
    req<GymMembership[]>(`/gyms/${gymId}/members`),
  addGymMember: (gymId: string, memberId: string, memberType: "fighter" | "coach") =>
    req<GymMembership>(`/gyms/${gymId}/members`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ member_id: memberId, member_type: memberType }),
    }),
  removeGymMember: (gymId: string, membershipId: number) =>
    req<void>(`/gyms/${gymId}/members/${membershipId}`, { method: "DELETE" }),
  importGymMember: (gymId: string, systemId: string) =>
    req<GymMembership>(`/gyms/${gymId}/members/import`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ system_id: systemId }),
    }),
  createGymMemberAccount: (gymId: string, data: { name: string; email: string; password: string; role: "fighter" | "coach" }) =>
    req<GymMembership>(`/gyms/${gymId}/members/create-account`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),

  // ---- Gym Managers ----
  listGymManagers: () => req<GymManager[]>("/gym-managers"),
  getGymManager: (id: string) => req<GymManager>(`/gym-managers/${id}`),
  createGymManager: (data: { name: string; gym_id: string; email?: string; phone?: string }) =>
    req<GymManager>("/gym-managers", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  updateGymManager: (id: string, patch: GymManagerPatch) =>
    req<GymManager>(`/gym-managers/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteGymManager: (id: string) =>
    req<void>(`/gym-managers/${id}`, { method: "DELETE" }),

  // ---- Photos ----
  uploadFighterPhoto: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const token =
      (typeof window !== "undefined" &&
        (localStorage.getItem("alion.token") ??
          sessionStorage.getItem("alion.token"))) ||
      null;
    const headers: Record<string, string> = {};
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const r = await fetch(`${BASE}/fighters/${id}/photo`, {
      method: "POST",
      body: fd,
      headers,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Fighter>;
  },
  photoUrl: (relativePath: string | null) =>
    relativePath
      ? `${BASE}/static/photos/${relativePath.replace(/^data\/photos\//, "")}`
      : null,

  // ---- Medical (fighters) ----
  getMedicalRecord: (fighterId: string) =>
    req<MedicalRecord | null>(`/fighters/${fighterId}/medical`),
  upsertMedicalRecord: (fighterId: string, patch: MedicalRecordPatch) =>
    req<MedicalRecord>(`/fighters/${fighterId}/medical`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  listAllergies: (fighterId: string) =>
    req<Allergy[]>(`/fighters/${fighterId}/allergies`),
  addAllergy: (
    fighterId: string,
    data: { substance: string; severity: AllergySeverity; notes?: string },
  ) =>
    req<Allergy>(`/fighters/${fighterId}/allergies`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteAllergy: (fighterId: string, allergyId: number) =>
    req<void>(`/fighters/${fighterId}/allergies/${allergyId}`, {
      method: "DELETE",
    }),
  listMedications: (fighterId: string) =>
    req<Medication[]>(`/fighters/${fighterId}/medications`),
  addMedication: (
    fighterId: string,
    data: {
      name: string;
      dose?: string;
      frequency?: string;
      started_on?: string;
      prescribed_by?: string;
      is_active?: boolean;
      notes?: string;
    },
  ) =>
    req<Medication>(`/fighters/${fighterId}/medications`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteMedication: (fighterId: string, medicationId: number) =>
    req<void>(`/fighters/${fighterId}/medications/${medicationId}`, {
      method: "DELETE",
    }),
  listConditions: (fighterId: string) =>
    req<MedicalCondition[]>(`/fighters/${fighterId}/conditions`),
  addCondition: (
    fighterId: string,
    data: {
      name: string;
      diagnosed_on?: string;
      status?: ConditionStatus;
      notes?: string;
    },
  ) =>
    req<MedicalCondition>(`/fighters/${fighterId}/conditions`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteCondition: (fighterId: string, conditionId: number) =>
    req<void>(`/fighters/${fighterId}/conditions/${conditionId}`, {
      method: "DELETE",
    }),

  // ---- Team: titles / sponsors / coach assignments ----
  listTitles: (fighterId: string) =>
    req<FighterTitle[]>(`/fighters/${fighterId}/titles`),
  addTitle: (
    fighterId: string,
    data: {
      name: string;
      organization?: string;
      weight_class?: string;
      won_on?: string;
      lost_on?: string;
      status?: TitleStatus;
      notes?: string;
    },
  ) =>
    req<FighterTitle>(`/fighters/${fighterId}/titles`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteTitle: (fighterId: string, titleId: number) =>
    req<void>(`/fighters/${fighterId}/titles/${titleId}`, { method: "DELETE" }),

  listSponsors: (fighterId: string) =>
    req<FighterSponsor[]>(`/fighters/${fighterId}/sponsors`),
  addSponsor: (
    fighterId: string,
    data: {
      name: string;
      started_on?: string;
      ended_on?: string;
      website?: string;
      notes?: string;
    },
  ) =>
    req<FighterSponsor>(`/fighters/${fighterId}/sponsors`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteSponsor: (fighterId: string, sponsorId: number) =>
    req<void>(`/fighters/${fighterId}/sponsors/${sponsorId}`, {
      method: "DELETE",
    }),

  listCoachAssignments: (fighterId: string) =>
    req<CoachAssignment[]>(`/fighters/${fighterId}/coach-assignments`),
  addCoachAssignment: (
    fighterId: string,
    data: {
      coach_id: string;
      role?: CoachRole;
      started_on?: string;
      ended_on?: string;
      notes?: string;
    },
  ) =>
    req<CoachAssignment>(`/fighters/${fighterId}/coach-assignments`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteCoachAssignment: (fighterId: string, assignmentId: number) =>
    req<void>(`/fighters/${fighterId}/coach-assignments/${assignmentId}`, {
      method: "DELETE",
    }),

  // ---- Detector evaluation (manual labels vs detections) ----
  getLabels: (sessionId: string) =>
    req<LabelsPayload | null>(`/sessions/${sessionId}/labels`),
  putLabels: (sessionId: string, labels: GroundTruthPunch[]) =>
    req<LabelsPayload>(`/sessions/${sessionId}/labels`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ labels }),
    }),
  deleteLabels: (sessionId: string) =>
    req<void>(`/sessions/${sessionId}/labels`, { method: "DELETE" }),
  sessionEvaluation: (sessionId: string, toleranceMs = 200) =>
    req<EvaluationResponse>(
      `/sessions/${sessionId}/evaluation?tolerance_ms=${toleranceMs}`,
    ),

  // Auth
  register: (email: string, password: string, name: string, role: UserRole = "fighter") =>
    req<AuthResponse>("/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, name, role }),
    }),
  login: (email: string, password: string) => {
    const body = new URLSearchParams();
    body.append("username", email);
    body.append("password", password);
    return fetch(`${BASE}/auth/login`, { method: "POST", body }).then(async (r) => {
      if (!r.ok) {
        const detail = await r.json().catch(() => ({ detail: "Login failed" }));
        throw new Error(detail.detail ?? "Login failed");
      }
      return r.json() as Promise<AuthResponse>;
    });
  },
  me: (token: string) =>
    fetch(`${BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    }).then(async (r) => {
      if (!r.ok) throw new Error("Not authenticated");
      return r.json() as Promise<AuthUser>;
    }),

  // Admin endpoints
  adminListUsers: () => req<AuthUser[]>("/auth/admin/users"),
  adminResetPassword: (userId: string, newPassword: string) =>
    req<{ status: string; message: string }>(`/auth/admin/users/${userId}/reset-password`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ new_password: newPassword }),
    }),
  adminUpdateUser: (userId: string, fields: Partial<Pick<AuthUser, "name" | "email" | "role" | "is_active">>) =>
    req<AuthUser>(`/auth/admin/users/${userId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields),
    }),
  adminDeleteUser: (userId: string) =>
    req<{ status: string; message: string }>(`/auth/admin/users/${userId}`, { method: "DELETE" }),
  adminDeactivateUser: (userId: string) =>
    req<{ status: string; message: string }>(`/auth/admin/users/${userId}/deactivate`, { method: "POST" }),
  adminActivateUser: (userId: string) =>
    req<{ status: string; message: string }>(`/auth/admin/users/${userId}/activate`, { method: "POST" }),
  adminStats: () => req<AdminSystemStats>("/auth/admin/stats"),
};

// ---- Evaluation types ----

export interface GroundTruthPunch {
  t_ms: number;
  hand: "left" | "right";
  punch_type?: "jab" | "cross" | "hook" | "uppercut" | null;
}

export interface LabelsPayload {
  labels: GroundTruthPunch[];
}

export interface AdminSystemStats {
  total_users: number;
  active_users: number;
  fighters: number;
  coaches: number;
  gym_managers: number;
  admins: number;
  gyms: number;
  sessions: number;
}

export interface EvaluationResponse {
  session_id: string;
  has_labels: boolean;
  label_count: number;
  detection_count: number;
  tolerance_ms: number;
  true_positives: number;
  false_positives: number;
  false_negatives: number;
  precision: number;
  recall: number;
  f1: number;
  mean_temporal_offset_ms: number;
  confusion: Record<string, Record<string, number>> | null;
  classes: string[];
}

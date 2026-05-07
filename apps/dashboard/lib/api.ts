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
  photo_path: string | null;
  created_at: string;
}

export type FighterPatch = Partial<Omit<Fighter, "id" | "created_at">>;

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
  fighterReadiness: (id: string) =>
    req<FighterReadiness | null>(`/fighters/${id}/readiness`),

  // ---- Coaches ----
  listCoaches: () => req<Coach[]>("/coaches"),
  getCoach: (id: string) => req<Coach>(`/coaches/${id}`),
  createCoach: (data: { name: string; gym?: string }) =>
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
    const r = await fetch(`${BASE}/coaches/${id}/photo`, {
      method: "POST",
      body: fd,
    });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<Coach>;
  },

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

  // ---- Photos ----
  uploadFighterPhoto: async (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await fetch(`${BASE}/fighters/${id}/photo`, {
      method: "POST",
      body: fd,
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

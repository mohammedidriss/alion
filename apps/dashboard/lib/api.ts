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
export type DetectionSource = "heuristic" | "lstm_v1";
export type VelocitySource = "world" | "image_heuristic";

export interface Fighter {
  id: string;
  name: string;
  dob: string | null;
  stance: Stance;
  created_at: string;
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
  updateFighter: (id: string, patch: { name?: string; stance?: Stance }) =>
    req<Fighter>(`/fighters/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(patch),
    }),
  deleteFighter: (id: string) =>
    req<void>(`/fighters/${id}`, { method: "DELETE" }),
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
  captureStatus: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/status`),
  listEvents: (id: string) => req<PunchEvent[]>(`/sessions/${id}/events`),
};

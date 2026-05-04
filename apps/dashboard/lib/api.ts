const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Stance = "orthodox" | "southpaw" | "switch";
export type SessionSource = "live_webcam" | "uploaded_video" | "live_iphone";
export type SessionStatus =
  | "pending"
  | "capturing"
  | "processing"
  | "completed"
  | "failed";
export type Hand = "left" | "right";
export type DetectionSource = "heuristic" | "lstm_v1";

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
  velocity_ms: number;
  detected_by: DetectionSource;
  confidence: number;
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
  createFighter: (name: string, stance: Stance = "orthodox") =>
    req<Fighter>("/fighters", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name, stance }),
    }),
  listSessions: () => req<Session[]>("/sessions"),
  getSession: (id: string) => req<Session>(`/sessions/${id}`),
  createSession: (fighter_id: string, source: SessionSource) =>
    req<Session>("/sessions", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ fighter_id, source }),
    }),
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
  startCapture: (id: string, max_frames?: number) =>
    req<CaptureStatus>(`/sessions/${id}/capture/start`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ max_frames }),
    }),
  captureStatus: (id: string) =>
    req<CaptureStatus>(`/sessions/${id}/capture/status`),
  listEvents: (id: string) => req<PunchEvent[]>(`/sessions/${id}/events`),
};

"use client";

import { useEffect, useState } from "react";
import { api, type Session, type PunchEvent } from "@/lib/api";

interface SessionMetrics {
  session: Session;
  events: PunchEvent[];
  punchCount: number;
  avgVelocity: number;
  punchTypes: Record<string, number>;
  detectionSources: Record<string, number>;
}

export default function ComparePage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [leftId, setLeftId] = useState<string>("");
  const [rightId, setRightId] = useState<string>("");
  const [left, setLeft] = useState<SessionMetrics | null>(null);
  const [right, setRight] = useState<SessionMetrics | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.listSessions().then((s) => {
      const completed = s.filter((x) => x.status === "completed");
      setSessions(completed);
    });
  }, []);

  const loadMetrics = async (id: string): Promise<SessionMetrics | null> => {
    if (!id) return null;
    const [session, events] = await Promise.all([
      api.getSession(id),
      api.listEvents(id),
    ]);
    const punchTypes: Record<string, number> = {};
    const detectionSources: Record<string, number> = {};
    let totalVel = 0;
    for (const e of events) {
      const t = e.punch_type ?? "unknown";
      punchTypes[t] = (punchTypes[t] ?? 0) + 1;
      detectionSources[e.detected_by] = (detectionSources[e.detected_by] ?? 0) + 1;
      totalVel += e.velocity_ms;
    }
    return {
      session,
      events,
      punchCount: events.length,
      avgVelocity: events.length > 0 ? totalVel / events.length : 0,
      punchTypes,
      detectionSources,
    };
  };

  const compare = async () => {
    setLoading(true);
    const [l, r] = await Promise.all([loadMetrics(leftId), loadMetrics(rightId)]);
    setLeft(l);
    setRight(r);
    setLoading(false);
  };

  // Filter sessions by backend for the dropdowns.
  const mediapipeSessions = sessions.filter((s) => s.pose_backend === "mediapipe");
  const yoloSessions = sessions.filter((s) => s.pose_backend === "yolov8");

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-8">
      <h1 className="text-2xl font-bold">Compare pose backends</h1>
      <p className="text-sm text-neutral-400">
        Select one MediaPipe session and one YOLOv8 session to compare punch detection performance side by side.
      </p>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-blue-800/50 bg-blue-950/20 p-4">
          <label className="mb-2 block text-sm font-medium text-blue-300">
            MediaPipe session
          </label>
          <select
            className="w-full rounded bg-neutral-900 p-2 text-sm"
            value={leftId}
            onChange={(e) => setLeftId(e.target.value)}
          >
            <option value="">Select…</option>
            {mediapipeSessions.map((s) => (
              <option key={s.id} value={s.id}>
                {new Date(s.started_at).toLocaleDateString()} — {s.frame_count} frames — {(s.duration_ms / 1000).toFixed(0)}s
              </option>
            ))}
            {mediapipeSessions.length === 0 && (
              <option disabled>No MediaPipe sessions yet</option>
            )}
          </select>
        </div>
        <div className="rounded-lg border border-purple-800/50 bg-purple-950/20 p-4">
          <label className="mb-2 block text-sm font-medium text-purple-300">
            YOLOv8 session
          </label>
          <select
            className="w-full rounded bg-neutral-900 p-2 text-sm"
            value={rightId}
            onChange={(e) => setRightId(e.target.value)}
          >
            <option value="">Select…</option>
            {yoloSessions.map((s) => (
              <option key={s.id} value={s.id}>
                {new Date(s.started_at).toLocaleDateString()} — {s.frame_count} frames — {(s.duration_ms / 1000).toFixed(0)}s
              </option>
            ))}
            {yoloSessions.length === 0 && (
              <option disabled>No YOLOv8 sessions yet</option>
            )}
          </select>
        </div>
      </div>

      <button
        onClick={compare}
        disabled={!leftId || !rightId || loading}
        className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
      >
        {loading ? "Loading…" : "Compare"}
      </button>

      {left && right && (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
          <MetricsCard metrics={left} color="blue" label="MediaPipe" />
          <MetricsCard metrics={right} color="purple" label="YOLOv8" />
        </div>
      )}
    </main>
  );
}

function MetricsCard({
  metrics,
  color,
  label,
}: {
  metrics: SessionMetrics;
  color: "blue" | "purple";
  label: string;
}) {
  const border = color === "blue" ? "border-blue-800/50" : "border-purple-800/50";
  const bg = color === "blue" ? "bg-blue-950/20" : "bg-purple-950/20";
  const accent = color === "blue" ? "text-blue-300" : "text-purple-300";

  return (
    <div className={`rounded-xl border ${border} ${bg} p-5 space-y-4`}>
      <h3 className={`text-lg font-semibold ${accent}`}>{label}</h3>

      <div className="grid grid-cols-2 gap-3">
        <Stat label="Total punches" value={metrics.punchCount} />
        <Stat label="Avg velocity (m/s)" value={metrics.avgVelocity.toFixed(2)} />
        <Stat label="Frames" value={metrics.session.frame_count} />
        <Stat label="Duration" value={`${(metrics.session.duration_ms / 1000).toFixed(1)}s`} />
      </div>

      <div>
        <h4 className="mb-1 text-xs font-medium text-neutral-400">Punch types</h4>
        <div className="flex flex-wrap gap-2">
          {Object.entries(metrics.punchTypes).map(([type, count]) => (
            <span
              key={type}
              className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-xs"
            >
              {type}: {count}
            </span>
          ))}
        </div>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-medium text-neutral-400">Detection sources</h4>
        <div className="flex flex-wrap gap-2">
          {Object.entries(metrics.detectionSources).map(([src, count]) => (
            <span
              key={src}
              className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-xs"
            >
              {src}: {count}
            </span>
          ))}
        </div>
      </div>

      <div>
        <h4 className="mb-1 text-xs font-medium text-neutral-400">Punches per minute</h4>
        <p className="text-lg font-semibold text-neutral-100">
          {metrics.session.duration_ms > 0
            ? ((metrics.punchCount / metrics.session.duration_ms) * 60000).toFixed(1)
            : "—"}
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <p className="text-xs text-neutral-500">{label}</p>
      <p className="text-lg font-semibold text-neutral-100">{value}</p>
    </div>
  );
}

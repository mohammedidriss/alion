"use client";

import { useEffect, useState } from "react";
import {
  api,
  type CaptureStatus,
  type PunchEvent,
  type Session,
} from "@/lib/api";

export default function SessionPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<CaptureStatus | null>(null);
  const [events, setEvents] = useState<PunchEvent[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const refresh = async () => {
    try {
      const [s, st, ev] = await Promise.all([
        api.getSession(id),
        api.captureStatus(id),
        api.listEvents(id),
      ]);
      setSession(s);
      setStatus(st);
      setEvents(ev);
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 1500);
    return () => clearInterval(t);
  }, [id]);

  const upload = async (file: File) => {
    setUploading(true);
    try {
      await api.uploadVideo(id, file);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setUploading(false);
    }
  };

  const start = async () => {
    try {
      await api.startCapture(id);
      await refresh();
    } catch (e) {
      setErr(String(e));
    }
  };

  if (!session) {
    return (
      <main className="p-8 text-sm text-neutral-400">
        {err ? <span className="text-red-400">{err}</span> : "Loading…"}
      </main>
    );
  }

  const counts = events.reduce(
    (acc, e) => ({ ...acc, [e.hand]: (acc[e.hand] ?? 0) + 1 }),
    {} as Record<string, number>,
  );

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Session</h1>
          <p className="font-mono text-xs text-neutral-500">{session.id}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-medium ${
            session.status === "completed"
              ? "bg-emerald-900 text-emerald-200"
              : session.status === "capturing" || session.status === "processing"
              ? "bg-amber-900 text-amber-200"
              : session.status === "failed"
              ? "bg-red-900 text-red-200"
              : "bg-neutral-800 text-neutral-300"
          }`}
        >
          {session.status}
        </span>
      </header>

      {err && <p className="text-sm text-red-400">{err}</p>}

      <section className="grid grid-cols-3 gap-3">
        <Stat label="Frames" value={status?.frame_count ?? 0} />
        <Stat
          label="Duration"
          value={`${((status?.duration_ms ?? 0) / 1000).toFixed(1)}s`}
        />
        <Stat label="Punches" value={status?.punch_count ?? 0} />
      </section>

      {session.source === "uploaded_video" && !session.video_path && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Upload MP4</h2>
          <input
            type="file"
            accept="video/mp4,video/quicktime"
            disabled={uploading}
            onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            className="mt-3 w-full text-sm"
          />
        </section>
      )}

      {((session.source === "live_webcam" && session.status === "pending") ||
        (session.source === "uploaded_video" &&
          session.video_path &&
          session.status === "pending")) && (
        <button
          onClick={start}
          className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500"
        >
          {session.source === "live_webcam" ? "Start live capture" : "Process video"}
        </button>
      )}

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">
          Punches{" "}
          <span className="text-sm text-neutral-500">
            (L {counts.left ?? 0} · R {counts.right ?? 0})
          </span>
        </h2>
        {events.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">No events yet.</p>
        ) : (
          <table className="mt-3 w-full text-sm">
            <thead className="text-left text-xs uppercase text-neutral-500">
              <tr>
                <th className="py-1">t (s)</th>
                <th>Hand</th>
                <th>Velocity (m/s)</th>
                <th>Conf</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i} className="border-t border-neutral-800">
                  <td className="py-1 font-mono">{(e.t_ms / 1000).toFixed(2)}</td>
                  <td className={e.hand === "left" ? "text-amber-300" : "text-sky-300"}>
                    {e.hand}
                  </td>
                  <td className="font-mono">{e.velocity_ms.toFixed(2)}</td>
                  <td className="font-mono">{e.confidence.toFixed(2)}</td>
                  <td className="text-neutral-500">{e.detected_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-neutral-800 p-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold">{value}</div>
    </div>
  );
}

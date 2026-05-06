"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { HrvPanel } from "@/components/HrvPanel";
import { PunchChart } from "@/components/PunchChart";
import { PunchTimeline } from "@/components/PunchTimeline";
import { VelocityHistogram } from "@/components/VelocityHistogram";
import {
  api,
  type Camera,
  type Capabilities,
  type CaptureStatus,
  type PunchEvent,
  type Session,
} from "@/lib/api";

export default function SessionPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<CaptureStatus | null>(null);
  const [events, setEvents] = useState<PunchEvent[]>([]);
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [cameraIndex, setCameraIndex] = useState<number>(0);

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
    api.capabilities().then(setCaps).catch(() => setCaps(null));
    api
      .listCameras()
      .then((r) => {
        setCameras(r.cameras);
        if (r.cameras.length > 0) setCameraIndex(r.cameras[0].index);
      })
      .catch(() => setCameras([]));
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
      await api.startCapture(id, { camera_index: cameraIndex });
      await refresh();
    } catch (e) {
      setErr(String(e));
    }
  };

  const stop = async () => {
    try {
      await api.stopCapture(id);
      await refresh();
    } catch (e) {
      setErr(String(e));
    }
  };

  const doDelete = async () => {
    try {
      await api.deleteSession(id);
      router.push(session?.fighter_id ? `/fighters/${session.fighter_id}` : "/");
    } catch (e) {
      setErr(String(e));
      setConfirmDelete(false);
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

  const cvAvailable = caps?.cv_available ?? true; // assume yes if check failed
  const showStart =
    session.status === "pending" &&
    (session.source === "live_webcam" ||
      (session.source === "uploaded_video" && !!session.video_path));

  return (
    <main className="mx-auto max-w-3xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        <Link
          href={session.fighter_id ? `/fighters/${session.fighter_id}` : "/"}
          className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-100"
        >
          <span aria-hidden>←</span> Back to fighter
        </Link>
        <button
          onClick={() => setConfirmDelete(true)}
          disabled={session.status === "capturing" || session.status === "processing"}
          title={
            session.status === "capturing" || session.status === "processing"
              ? "Stop the capture before deleting."
              : undefined
          }
          className="text-sm text-red-400 hover:text-red-300 disabled:cursor-not-allowed disabled:text-neutral-600"
        >
          Delete session
        </button>
      </div>

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

      {!cvAvailable && (
        <div className="rounded-lg border border-amber-700/60 bg-amber-950/40 p-4 text-sm">
          <p className="font-medium text-amber-200">
            Capture isn&apos;t available on this server
          </p>
          <p className="mt-1 text-amber-100/80">
            {caps?.cv_reason ??
              "MediaPipe / OpenCV are not installed in this environment."}
          </p>
          <p className="mt-2 text-amber-100/70">
            Run capture on the macOS host:{" "}
            <code className="rounded bg-black/40 px-1.5 py-0.5 font-mono text-xs">
              uv run python scripts/{session.source === "live_webcam" ? "record_live.py" : "process_video.py"}
            </code>
          </p>
        </div>
      )}

      {session.status === "failed" && session.failure_reason && (
        <div className="rounded-lg border border-red-700/60 bg-red-950/40 p-4 text-sm">
          <p className="font-medium text-red-200">Capture failed</p>
          <p className="mt-1 text-red-100/80">{session.failure_reason}</p>
        </div>
      )}

      <section className="grid grid-cols-3 gap-3">
        <Stat label="Frames" value={status?.frame_count ?? 0} />
        <Stat
          label="Duration"
          value={`${((status?.duration_ms ?? 0) / 1000).toFixed(1)}s`}
        />
        <Stat label="Punches" value={status?.punch_count ?? 0} />
      </section>

      {(session.status === "capturing" || session.status === "processing") && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">Camera</h2>
            <span className="flex items-center gap-2 text-xs text-neutral-400">
              <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-red-500" />
              live
            </span>
          </div>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={session.id}
            src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/sessions/${session.id}/preview`}
            alt="live capture preview with pose overlay"
            className="mt-3 w-full rounded border border-neutral-800 bg-black"
          />
          <p className="mt-2 text-xs text-neutral-500">
            Skeleton overlay drawn from MediaPipe landmarks. Frames stream at
            ~15 fps; capture itself runs at the source&apos;s native rate.
          </p>
        </section>
      )}

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

      {showStart && session.source === "live_webcam" && cameras.length > 0 && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <label className="text-sm font-medium text-neutral-300">Camera</label>
          <select
            className="mt-2 w-full rounded bg-neutral-900 p-2 text-sm"
            value={cameraIndex}
            onChange={(e) => setCameraIndex(Number(e.target.value))}
          >
            {cameras.map((c) => (
              <option key={c.index} value={c.index}>
                #{c.index} — {c.width}×{c.height} @ {Math.round(c.fps)} fps
              </option>
            ))}
          </select>
          <p className="mt-2 text-xs text-neutral-500">
            {cameras.length} camera{cameras.length === 1 ? "" : "s"} available.
          </p>
        </section>
      )}

      {showStart && (
        <button
          onClick={start}
          disabled={!cvAvailable}
          title={
            cvAvailable
              ? undefined
              : "Disabled — capture is not available on this server. Run on the host."
          }
          className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400 disabled:hover:bg-neutral-700"
        >
          {session.source === "live_webcam" ? "Start live capture" : "Process video"}
        </button>
      )}

      {(session.status === "capturing" || session.status === "processing") && (
        <button
          onClick={stop}
          className="rounded bg-red-600 px-4 py-2 font-medium hover:bg-red-500"
        >
          Stop capture
        </button>
      )}

      {(session.source === "polar_h10_only" ||
        session.source === "hrv_replay") && <HrvPanel sessionId={session.id} />}

      <PunchChart events={events} />

      {events.length > 0 && status?.duration_ms && status.duration_ms > 0 && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Timeline</h2>
          <p className="mt-1 text-xs text-neutral-500">
            Each dot is a detected punch; size scales with peak velocity.
            Hover for details.
          </p>
          <div className="mt-3">
            <PunchTimeline events={events} durationMs={status.duration_ms} />
          </div>
        </section>
      )}

      {events.length > 1 && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Velocity distribution</h2>
          <p className="mt-1 text-xs text-neutral-500">
            How your punches stack across the velocity range. Bars stack
            left + right counts within each bucket.
          </p>
          <div className="mt-3">
            <VelocityHistogram events={events} />
          </div>
        </section>
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
                <th className="py-1">#</th>
                <th>Hand</th>
                <th>Time</th>
                <th>Velocity (m/s)</th>
                <th>Conf</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i} className="border-t border-neutral-800">
                  <td className="py-1 font-mono text-xs text-neutral-500">{i + 1}</td>
                  <td className={e.hand === "left" ? "text-amber-300" : "text-sky-300"}>
                    {e.hand}
                  </td>
                  <td className="font-mono">{formatPunchTime(session.started_at, e.t_ms)}</td>
                  <td className="font-mono">{e.velocity_ms.toFixed(2)}</td>
                  <td className="font-mono">{e.confidence.toFixed(2)}</td>
                  <td className="text-neutral-500">{e.detected_by}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
          <div className="w-full max-w-md rounded-lg border border-neutral-800 bg-neutral-950 p-5 shadow-xl">
            <h3 className="font-medium">Delete this session?</h3>
            <p className="mt-2 text-sm text-neutral-400">
              This removes the session row, all detected punch events, captured
              pose data, and any uploaded video file. Cannot be undone.
            </p>
            <div className="mt-4 flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(false)}
                className="rounded bg-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-600"
              >
                Cancel
              </button>
              <button
                onClick={doDelete}
                className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium hover:bg-red-500"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
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

/**
 * Convert (session start, offset ms) → "h:mm:ss AM/PM" wall-clock time.
 * Server returns started_at as an ISO timestamp in UTC; the browser's
 * `new Date(...)` parses it and `toLocaleTimeString` renders in the
 * user's local timezone with their locale's preferred 12/24-hour format.
 */
function formatPunchTime(sessionStartedAt: string, eventTMs: number): string {
  const startMs = new Date(sessionStartedAt).getTime();
  if (Number.isNaN(startMs)) return "—";
  const d = new Date(startMs + eventTMs);
  return d.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
}

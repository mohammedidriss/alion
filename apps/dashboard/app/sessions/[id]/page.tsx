"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { EvaluationCard } from "@/components/EvaluationCard";
import { FighterBackLink } from "@/components/FighterBackLink";
import { HrvPanel } from "@/components/HrvPanel";
import { IMUPanel } from "@/components/IMUPanel";
import { DetectorComparisonCard } from "@/components/DetectorComparisonCard";
import { LiveAdviceCard } from "@/components/LiveAdviceCard";
import { RQ1RaterCard } from "@/components/RQ1RaterCard";
import { PunchChart } from "@/components/PunchChart";
import { PunchTimeline } from "@/components/PunchTimeline";
import {
  AttachmentsCard,
  RoundConfigCard,
  RoundTimer,
} from "@/components/SessionRounds";
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
  const [notesDraft, setNotesDraft] = useState<string>("");
  const [notesDirty, setNotesDirty] = useState(false);
  const [baselineUploading, setBaselineUploading] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  // Manual-pause bookkeeping. Timer freezes only when the user hits the
  // pause button — not when auto-rest pauses the camera (the timer must
  // keep counting through rest so it can flip back to round).
  const [manualPauseStart, setManualPauseStart] = useState<number | null>(null);
  const [manualPauseAccumMs, setManualPauseAccumMs] = useState(0);
  // Resume countdown — when the user clicks Resume, we tick 3 → 1 on
  // the camera panel before actually telling the API to resume, so
  // the fighter has time to get back on guard.
  const [resumeCountdown, setResumeCountdown] = useState<number | null>(null);

  useEffect(() => {
    if (session?.status !== "capturing") return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [session?.status]);

  // Auto-pause capture during rest, auto-resume during rounds. Skips
  // recording rest frames so the saved video stays small. Reads phase
  // from elapsed wall-clock since started_at.
  const lastPhaseRef = useRef<"round" | "rest" | "done" | null>(null);
  useEffect(() => {
    if (session?.status !== "capturing" || !session.started_at) return;
    const livePauseMs =
      manualPauseStart != null ? now - manualPauseStart : 0;
    const elapsedS =
      (now - parseUtc(session.started_at).getTime() -
        manualPauseAccumMs - livePauseMs) /
      1000;
    const rounds = session.round_count ?? 3;
    const roundS = session.round_duration_s ?? 3;
    const restS = session.rest_duration_s ?? 3;
    const totalS = rounds * roundS + Math.max(0, rounds - 1) * restS;
    let phase: "round" | "rest" | "done" = "done";
    if (elapsedS < totalS) {
      let acc = 0;
      for (let i = 1; i <= rounds; i++) {
        if (elapsedS < acc + roundS) {
          phase = "round";
          break;
        }
        acc += roundS;
        if (i < rounds && elapsedS < acc + restS) {
          phase = "rest";
          break;
        }
        acc += restS;
      }
    }
    const prev = lastPhaseRef.current;
    if (prev !== phase) {
      lastPhaseRef.current = phase;
      if (prev === "round" && phase === "rest" && !status?.is_paused) {
        api.pauseCapture(id).catch(() => undefined);
      } else if (prev === "rest" && phase === "round" && status?.is_paused) {
        api.resumeCapture(id).catch(() => undefined);
      }
    }
    // Auto-stop the session once the planned rounds are done. Only fire
    // once — refresh() will flip status to "completed" on the next poll.
    if (phase === "done" && session?.status === "capturing") {
      api.stopCapture(id).catch(() => undefined);
    }
  }, [
    now,
    session?.status,
    session?.started_at,
    session?.round_count,
    session?.round_duration_s,
    session?.rest_duration_s,
    status?.is_paused,
    id,
  ]);

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
      // Only sync notes from the server if the user hasn't typed unsaved
      // changes in the textarea.
      if (!notesDirty) setNotesDraft(s.notes ?? "");
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

  const pause = async () => {
    try {
      await api.pauseCapture(id);
      setManualPauseStart(Date.now());
      await refresh();
    } catch (e) {
      setErr(String(e));
    }
  };

  const resume = async () => {
    // Kick off a visible 3 → 1 countdown on the camera panel; the
    // actual /capture/resume call fires when the count reaches 0.
    if (resumeCountdown !== null) return; // already counting
    setResumeCountdown(3);
  };

  // Tick the resume countdown each second; on hitting 0 the API call
  // fires and the manual-pause window is closed.
  useEffect(() => {
    if (resumeCountdown === null) return;
    if (resumeCountdown <= 0) {
      (async () => {
        try {
          await api.resumeCapture(id);
          if (manualPauseStart != null) {
            setManualPauseAccumMs((a) => a + (Date.now() - manualPauseStart));
            setManualPauseStart(null);
          }
          await refresh();
        } catch (e) {
          setErr(String(e));
        } finally {
          setResumeCountdown(null);
        }
      })();
      return;
    }
    const t = setTimeout(() => setResumeCountdown((c) => (c == null ? null : c - 1)), 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeCountdown]);

  const reprocess = async () => {
    try {
      await api.reprocessCapture(id);
      await refresh();
    } catch (e) {
      setErr(String(e));
    }
  };

  const uploadBaseline = async (file: File) => {
    setBaselineUploading(true);
    try {
      await api.uploadBaseline(id, file);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBaselineUploading(false);
    }
  };

  const saveNotes = async () => {
    try {
      await api.annotateSession(id, notesDraft);
      setNotesDirty(false);
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

  const isLive =
    session.status === "capturing" || session.status === "processing";
  const liveDurationMs = isLive
    ? session.status === "capturing" && session.started_at
      ? Math.max(
          0,
          now -
            parseUtc(session.started_at).getTime() -
            manualPauseAccumMs -
            (manualPauseStart != null ? now - manualPauseStart : 0),
        )
      : status?.duration_ms ?? 0
    : status?.duration_ms ?? 0;

  return (
    <main className="mx-auto max-w-7xl space-y-6 p-8">
      <div className="flex items-center justify-between">
        {session.fighter_id ? (
          <FighterBackLink fighterId={session.fighter_id} />
        ) : (
          <Link
            href="/"
            className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-100"
          >
            <span aria-hidden>←</span> Back home
          </Link>
        )}
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
        <div className="flex items-center gap-4">
          <div>
            <h1 className="text-2xl font-semibold">Session</h1>
            <p className="font-mono text-xs text-neutral-500">{session.id}</p>
          </div>
          <Link
            href={`/sessions/${id}/corner`}
            className="rounded bg-amber-600/20 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-600/30"
          >
            🥊 Gym Mode
          </Link>
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

      {/* Top action bar — controls + (when live) the camera preview.
          Sits above the main 3-column layout so the primary capture
          controls and the live skeleton overlay are always above the
          fold regardless of state. */}
      {(showStart ||
        isLive ||
        (session.source === "uploaded_video" && !session.video_path)) && (
        <section
          className={`relative space-y-4 rounded-lg border p-4 transition-colors ${
            status?.is_paused
              ? "border-red-500 bg-red-700/30"
              : "border-neutral-800 bg-neutral-950/60"
          }`}
        >
          {/* Round timer pinned at the top of the capture panel during
              live capture so the fighter can read elapsed/round-left
              while looking at the camera. */}
          {isLive && (
            <RoundTimer
              session={session}
              durationMs={liveDurationMs}
              isPaused={!!status?.is_paused}
            />
          )}
          <div
            className={`grid grid-cols-1 gap-4 ${
              isLive ? "lg:grid-cols-[1fr_minmax(0,420px)]" : ""
            }`}
          >
            {/* Live preview: only visible during capture. Lives in the
                same panel as the capture controls so "what the camera sees"
                is co-located with start/pause/stop. */}
            {isLive && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-medium">Camera</h2>
                  <span
                    className={`flex items-center gap-2 text-xs ${
                      status?.is_paused ? "text-red-200" : "text-neutral-400"
                    }`}
                  >
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${
                        status?.is_paused ? "bg-red-500" : "animate-pulse bg-red-500"
                      }`}
                    />
                    {status?.is_paused ? "paused" : "live"}
                  </span>
                </div>
                <div className="relative">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    key={session.id}
                    src={`${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/sessions/${session.id}/preview`}
                    alt="live capture preview with pose overlay"
                    className="w-full rounded border border-neutral-800 bg-black"
                  />
                  {(status?.is_paused || resumeCountdown !== null) && (
                    <div className="absolute inset-0 flex items-center justify-center rounded bg-red-700/60">
                      {resumeCountdown !== null && resumeCountdown > 0 ? (
                        <span className="text-[12rem] font-black leading-none text-white drop-shadow-2xl">
                          {resumeCountdown}
                        </span>
                      ) : (
                        <span className="text-7xl font-black uppercase tracking-widest text-white drop-shadow-lg">
                          Paused
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <p className="text-[11px] text-neutral-500">
                  Skeleton overlay from MediaPipe; preview at ~15 fps,
                  capture at native rate.
                </p>
              </div>
            )}

            {/* Controls column. */}
            <div className="flex flex-wrap items-end gap-3">
              {session.source === "uploaded_video" && !session.video_path && (
                <div className="flex flex-col">
                  <label className="mb-1 text-xs text-neutral-400">Upload MP4</label>
                  <input
                    type="file"
                    accept="video/mp4,video/quicktime"
                    disabled={uploading}
                    onChange={(e) =>
                      e.target.files?.[0] && upload(e.target.files[0])
                    }
                    className="text-xs"
                  />
                </div>
              )}
              {showStart &&
                session.source === "live_webcam" &&
                cameras.length > 0 && (
                  <div className="flex flex-col">
                    <label className="mb-1 text-xs text-neutral-400">Camera</label>
                    <select
                      className="rounded bg-neutral-900 px-3 py-2 text-sm"
                      value={cameraIndex}
                      onChange={(e) => setCameraIndex(Number(e.target.value))}
                    >
                      {cameras.map((c) => (
                        <option key={c.index} value={c.index}>
                          #{c.index} — {c.width}×{c.height} @ {Math.round(c.fps)} fps
                        </option>
                      ))}
                    </select>
                  </div>
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
                  className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
                >
                  {session.source === "live_webcam"
                    ? "Start live capture"
                    : "Process video"}
                </button>
              )}
              {isLive && (
                <>
                  {status?.is_paused ? (
                    <button
                      onClick={resume}
                      disabled={resumeCountdown !== null}
                      className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500 disabled:cursor-wait disabled:bg-neutral-700"
                    >
                      {resumeCountdown !== null ? `Resuming in ${resumeCountdown}…` : "Resume"}
                    </button>
                  ) : (
                    <button
                      onClick={pause}
                      className="rounded bg-amber-600 px-4 py-2 font-medium hover:bg-amber-500"
                    >
                      Pause
                    </button>
                  )}
                  <button
                    onClick={stop}
                    className="rounded bg-red-600 px-4 py-2 font-medium hover:bg-red-500"
                  >
                    Stop capture
                  </button>
                  {status?.is_paused && (
                    <span className="self-center text-xs text-amber-300">
                      paused
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        </section>
      )}

      {/* 3-col layout: timer + round config (left), all metrics +
          analysis (middle), AI corner advice (right). Stacks on mobile. */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
          <RoundConfigCard session={session} onChange={setSession} />
        </aside>
        <div className="space-y-6">
          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Frames" value={status?.frame_count ?? 0} />
            <Stat
              label="Duration"
              value={`${((status?.duration_ms ?? 0) / 1000).toFixed(1)}s`}
            />
            <Stat label="Punches" value={status?.punch_count ?? 0} />
            <Stat
              label="Punches / min"
              value={(() => {
                const ms = status?.duration_ms ?? 0;
                const n = status?.punch_count ?? 0;
                if (!ms || !n) return "—";
                const ppm = (n / (ms / 1000)) * 60;
                return ppm.toFixed(0);
              })()}
            />
          </section>

      {(() => {
        // Always show Session performance — placeholders ("—") when
        // no events yet so the panel structure is visible during a
        // fresh capture before the first detection lands.
        const durationMs = status?.duration_ms ?? 0;
        const hasData = events.length > 0 && durationMs > 0;
        let peakP90: number | null = null;
        let ppm: number | null = null;
        let score: number | null = null;
        let durationMin = durationMs / 60_000;
        if (hasData) {
          const sorted = [...events]
            .map((e) => e.velocity_ms)
            .sort((a, b) => a - b);
          const k = (sorted.length - 1) * 0.9;
          const lo = Math.floor(k);
          const hi = Math.min(lo + 1, sorted.length - 1);
          peakP90 = sorted[lo] * (1 - (k - lo)) + sorted[hi] * (k - lo);
          ppm = events.length / Math.max(durationMin, 1e-6);
          score = peakP90 * (ppm / 60) * durationMin;
        }
        const fmt = (v: number | null, d = 2) => (v === null ? "—" : v.toFixed(d));
        return (
          <section className="rounded-lg border border-neutral-800 bg-neutral-950 p-4">
            <h2 className="font-medium">Session performance</h2>
            <p className="mt-1 text-xs text-neutral-500">
              Transparent v1: peak_v_p90 × ppm/60 × duration_min. Same
              formula as the per-fighter progress chart.
            </p>
            <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded border border-neutral-800 p-3">
                <div className="text-xs text-neutral-500">Peak v p90</div>
                <div className="mt-1 text-xl font-semibold tabular-nums">
                  {fmt(peakP90)} <span className="text-xs text-neutral-500">m/s</span>
                </div>
              </div>
              <div className="rounded border border-neutral-800 p-3">
                <div className="text-xs text-neutral-500">Throughput</div>
                <div className="mt-1 text-xl font-semibold tabular-nums">
                  {fmt(ppm, 0)} <span className="text-xs text-neutral-500">ppm</span>
                </div>
              </div>
              <div className="rounded border border-neutral-800 p-3">
                <div className="text-xs text-neutral-500">Duration</div>
                <div className="mt-1 text-xl font-semibold tabular-nums">
                  {durationMin > 0 ? durationMin.toFixed(2) : "—"}{" "}
                  <span className="text-xs text-neutral-500">min</span>
                </div>
              </div>
              <div className="rounded border border-amber-700/40 bg-amber-950/30 p-3">
                <div className="text-xs text-amber-300/80">Score</div>
                <div className="mt-1 text-xl font-semibold tabular-nums text-amber-100">
                  {fmt(score)}
                </div>
              </div>
            </div>
            {!hasData && (
              <p className="mt-3 text-[11px] text-neutral-500">
                Waiting for the first detected punch — metrics populate live as the detector fires.
              </p>
            )}
          </section>
        );
      })()}

      {(() => {
        // Always show the hardest-punch panel; placeholders when no
        // events yet so the user sees the structure during a fresh
        // capture.
        const hardest =
          events.length > 0
            ? events.reduce(
                (m, e) => (e.velocity_ms > m.velocity_ms ? e : m),
                events[0],
              )
            : null;
        return (
          <section className="rounded-lg border border-amber-700/40 bg-gradient-to-br from-amber-950/30 to-neutral-950 p-4">
            <div className="flex items-baseline justify-between">
              <h2 className="font-medium text-amber-200">Hardest punch</h2>
              <span className="text-xs text-neutral-500">
                {hardest ? formatPunchTime(session.started_at, hardest.t_ms) : "—"}
              </span>
            </div>
            <div className="mt-3 flex items-baseline gap-3">
              <span className="text-4xl font-bold tabular-nums text-amber-100">
                {hardest ? hardest.velocity_ms.toFixed(2) : "—"}
              </span>
              <span className="text-sm text-neutral-400">m/s</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
              <span>
                hand:{" "}
                <span
                  className={
                    hardest?.hand === "left"
                      ? "text-amber-300"
                      : hardest?.hand === "right"
                        ? "text-sky-300"
                        : "text-neutral-500"
                  }
                >
                  {hardest?.hand ?? "—"}
                </span>
              </span>
              {hardest?.punch_type && <span>type: {hardest.punch_type}</span>}
              {hardest?.lead_or_rear && <span>{hardest.lead_or_rear}</span>}
              <span>
                conf: {hardest ? hardest.confidence.toFixed(2) : "—"}
              </span>
            </div>
            {!hardest && (
              <p className="mt-3 text-[11px] text-neutral-500">
                Will surface the highest-velocity detection of this session as soon as one fires.
              </p>
            )}
          </section>
        );
      })()}


      {events.length >= 5 &&
        (() => {
          const meanConf =
            events.reduce((s, e) => s + e.confidence, 0) / events.length;
          if (meanConf >= 0.7) return null;
          return (
            <div className="rounded-lg border border-amber-700/60 bg-amber-950/40 p-3 text-sm">
              <p className="font-medium text-amber-200">Low pose quality</p>
              <p className="mt-1 text-xs text-amber-100/80">
                Mean detection confidence is {meanConf.toFixed(2)} (threshold
                0.70). Try better lighting, framing the full upper body, or
                moving closer to the camera for more reliable detections.
              </p>
            </div>
          );
        })()}

      {/* Detector evaluation — labels-vs-detections accuracy.
          Shown for any completed session; the card itself handles the
          "no labels yet" empty state. */}
      {session.status === "completed" && events.length > 0 && (
        <EvaluationCard sessionId={id} />
      )}

      <HrvPanel sessionId={session.id} />
      <IMUPanel sessionId={session.id} punchEvents={events} />
      <RQ1RaterCard sessionId={session.id} />

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
        <h2 className="font-medium">Pre-session HRV baseline</h2>
        <p className="mt-1 text-xs text-neutral-500">
          Upload a 5-min resting RR-interval CSV (single column{" "}
          <code className="rounded bg-neutral-900 px-1 font-mono">rr_ms</code>{" "}
          or two columns{" "}
          <code className="rounded bg-neutral-900 px-1 font-mono">
            t_ms,rr_ms
          </code>
          ) recorded just before warmup. Used as the readiness signal in the
          fighter performance matrix.
        </p>
        {session.baseline_rmssd_ms != null ? (
          <div className="mt-3 flex flex-wrap gap-3 text-sm">
            <span className="rounded bg-emerald-900/40 px-2 py-1 text-emerald-200">
              RMSSD {session.baseline_rmssd_ms.toFixed(1)} ms
            </span>
            <span className="rounded bg-emerald-900/40 px-2 py-1 text-emerald-200">
              SDNN {session.baseline_sdnn_ms?.toFixed(1) ?? "—"} ms
            </span>
            <span className="rounded bg-emerald-900/40 px-2 py-1 text-emerald-200">
              Mean HR {session.baseline_mean_hr_bpm?.toFixed(0) ?? "—"} bpm
            </span>
            {session.baseline_recorded_at && (
              <span className="self-center text-xs text-neutral-500">
                recorded{" "}
                {new Date(session.baseline_recorded_at).toLocaleString()}
              </span>
            )}
          </div>
        ) : session.status === "pending" ? (
          <input
            type="file"
            accept=".csv,text/csv"
            disabled={baselineUploading}
            onChange={(e) =>
              e.target.files?.[0] && uploadBaseline(e.target.files[0])
            }
            className="mt-3 w-full text-sm"
          />
        ) : (
          <p className="mt-3 text-sm text-neutral-500">
            No baseline recorded for this session.
          </p>
        )}
      </section>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">Notes &amp; tags</h2>
        <p className="mt-1 text-xs text-neutral-500">
          Free-form notes for this session. Useful tags: shadowboxing, bag,
          mitts, sparring.
        </p>
        <textarea
          rows={3}
          value={notesDraft}
          onChange={(e) => {
            setNotesDraft(e.target.value);
            setNotesDirty(true);
          }}
          placeholder="e.g. shadowboxing — focus on jab footwork"
          className="mt-2 w-full rounded bg-neutral-900 p-2 text-sm"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={saveNotes}
            disabled={!notesDirty}
            className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500 disabled:bg-neutral-700 disabled:text-neutral-400"
          >
            {notesDirty ? "Save notes" : "Saved"}
          </button>
          {notesDirty && (
            <button
              onClick={() => {
                setNotesDraft(session.notes ?? "");
                setNotesDirty(false);
              }}
              className="text-xs text-neutral-400 hover:text-neutral-100"
            >
              Discard
            </button>
          )}
        </div>
      </section>

      {/* Generic file uploads attached to this session — extra videos,
          sparring photos, coach notes PDFs, etc. */}
      <AttachmentsCard sessionId={id} />

      {events.length > 0 && (
        <section className="rounded-lg border border-neutral-800 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="font-medium">Export</h2>
            <a
              href={api.eventsCsvUrl(id)}
              download={`alion-${id}-events.csv`}
              className="rounded bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700"
            >
              Download events CSV
            </a>
          </div>
          {session.source === "uploaded_video" && session.video_path && (
            <div className="mt-3 flex items-center gap-2">
              <button
                onClick={reprocess}
                disabled={
                  session.status === "capturing" ||
                  session.status === "processing"
                }
                className="rounded bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700 disabled:cursor-not-allowed disabled:bg-neutral-900 disabled:text-neutral-600"
                title="Re-runs the pipeline on the uploaded video. Existing events are wiped first."
              >
                Re-process video
              </button>
              <span className="text-xs text-neutral-500">
                Re-runs detection on the uploaded video. Existing events are
                replaced.
              </span>
            </div>
          )}
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
                <th>Type</th>
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
                  <td className="capitalize text-neutral-300">{e.punch_type || "—"}</td>
                  <td className="font-mono">{formatPunchTime(session.started_at, e.t_ms)}</td>
                  <td className="font-mono">{e.velocity_ms.toFixed(2)}</td>
                  <td className="font-mono">{e.confidence.toFixed(2)}</td>
                  <td className="text-neutral-500">
                    {e.detected_by === "custom_ml" ? "ML" : e.detected_by}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
        </div>
        <aside className="space-y-4 xl:sticky xl:top-4 xl:self-start">
          <LiveAdviceCard sessionId={session.id} status={session.status} />
          <DetectorComparisonCard
            sessionId={session.id}
            status={session.status}
          />
        </aside>
      </div>

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

function parseUtc(s: string): Date {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(s) ? s : s + "Z");
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

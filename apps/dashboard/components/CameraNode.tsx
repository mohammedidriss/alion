"use client";

/**
 * CameraNode (ADR-010) — one capture device. Registers to a session with the join
 * token, previews the feed, runs MediaPipe pose + the punch detector, records, and
 * on the coach's synchronized start flips to RECORDING and uploads its clip + pose.
 *
 * Used by the phone camera page (/sessions/[id]/camera) and embedded directly in
 * the coach's session page so the laptop can be a camera without opening a link.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { PunchDetector } from "@/lib/punchDetector";
import { api } from "@/lib/api";

type Phase = "connecting" | "ready" | "countdown" | "recording" | "stopped" | "error";

const LABELS = ["front", "left", "right", "45-left", "45-right", "overhead"];

export function CameraNode({
  sessionId,
  token,
  defaultLabel = "front",
  tile = false,
  onDeviceId,
}: {
  sessionId: string;
  token: string;
  defaultLabel?: string;
  /** Render as a single grid tile (video + overlay only) — used for the laptop
   *  inside the coach's 2×2 cameras grid. */
  tile?: boolean;
  onDeviceId?: (deviceId: string) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const deviceIdRef = useRef<string | null>(null);
  const offsetRef = useRef(0); // server clock − local clock (ms)
  const recStartRef = useRef<number | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const landmarkerRef = useRef<unknown>(null);
  const detectorRef = useRef<PunchDetector>(new PunchDetector(null));
  const rafRef = useRef<number>(0);
  const punchCountRef = useRef(0);
  const pausedRef = useRef(false); // gates the pose loop while the coach has paused
  const pauseStartRef = useRef<number | null>(null); // when the current pause began
  const pausedAccumRef = useRef(0); // total paused ms, subtracted from elapsed
  const poseRef = useRef<
    { t_ms: number; landmarks: number[][]; world_landmarks: number[][] | null }[]
  >([]);

  const [phase, setPhase] = useState<Phase>("connecting");
  const [noCamera, setNoCamera] = useState(false);
  const [camError, setCamError] = useState<string | null>(null);
  const [recInfo, setRecInfo] = useState<string | null>(null);
  const [label, setLabel] = useState(defaultLabel);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [uploaded, setUploaded] = useState(false);
  const [punchCount, setPunchCount] = useState(0);
  const [paused, setPaused] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // Open the camera + register as a device.
  useEffect(() => {
    if (!token) {
      setErr("Missing join token.");
      setPhase("error");
      return;
    }
    let stream: MediaStream | null = null;
    let cancelled = false;
    (async () => {
      try {
        // Camera preview is best-effort: if it fails (no camera, or not a secure
        // context) the device still registers and joins the sync.
        try {
          if (!navigator.mediaDevices?.getUserMedia) throw new Error("no getUserMedia");
          stream = await navigator.mediaDevices.getUserMedia({
            video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 } },
            audio: true, // needed later for bell/audio sync
          });
          streamRef.current = stream;
          if (!cancelled && videoRef.current) {
            videoRef.current.srcObject = stream;
            videoRef.current.play().catch(() => {}); // iOS Safari needs an explicit play()
          }
        } catch (camErr) {
          if (!cancelled) {
            setNoCamera(true);
            setCamError(
              camErr instanceof Error ? `${camErr.name}: ${camErr.message}` : "camera error",
            );
          }
        }
        if (cancelled) return;
        const { device_id } = await api.multicamRegister(sessionId, token, "camera", defaultLabel);
        deviceIdRef.current = device_id;
        onDeviceId?.(device_id);
        setPhase("ready");
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Could not register with the session.");
        setPhase("error");
      }
    })();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, token]);

  // Heartbeat + poll the coach's command; drive the synchronized start.
  useEffect(() => {
    if (phase === "connecting" || phase === "error") return;
    let alive = true;
    const tick = async () => {
      const did = deviceIdRef.current;
      if (!did) return;
      try {
        const status = pausedRef.current
          ? "paused"
          : phase === "recording"
            ? "recording"
            : "ready";
        const st = await api.multicamHeartbeat(sessionId, token, did, status, punchCountRef.current);
        offsetRef.current = st.server_now_ms - Date.now();
        if (st.command === "start" && st.start_at_ms != null) {
          const localStart = st.start_at_ms - offsetRef.current;
          const msLeft = localStart - Date.now();
          if (msLeft > 0) {
            setPhase("countdown");
            setCountdown(Math.ceil(msLeft / 1000));
          } else if (!recStartRef.current) {
            recStartRef.current = localStart;
            setPhase("recording");
          }
          // Pause / resume — the coach toggles st.paused. Hold or continue the SAME
          // clip and freeze the punch loop, without ending the recording.
          const wantPaused = !!st.paused;
          if (recStartRef.current && wantPaused !== pausedRef.current) {
            pausedRef.current = wantPaused;
            setPaused(wantPaused);
            const rec = recorderRef.current;
            if (wantPaused) {
              pauseStartRef.current = Date.now();
              if (rec && rec.state === "recording") rec.pause();
            } else {
              if (pauseStartRef.current != null) {
                pausedAccumRef.current += Date.now() - pauseStartRef.current;
                pauseStartRef.current = null;
              }
              if (rec && rec.state === "paused") rec.resume();
            }
          }
        } else if (st.command === "stop") {
          recStartRef.current = null;
          setPhase("stopped");
        }
      } catch {
        if (alive) setErr("Lost the connection to the session.");
      }
    };
    const id = setInterval(tick, 400);
    tick();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [phase, sessionId, token]);

  // Recording elapsed timer — paused time is subtracted so it freezes on Pause.
  useEffect(() => {
    if (phase !== "recording") return;
    const id = setInterval(() => {
      if (!recStartRef.current) return;
      const inPause = pauseStartRef.current != null ? Date.now() - pauseStartRef.current : 0;
      setElapsed(
        (Date.now() - recStartRef.current - pausedAccumRef.current - inPause) / 1000,
      );
    }, 200);
    return () => clearInterval(id);
  }, [phase]);

  // Real capture: start MediaRecorder on the synchronized start, upload on stop.
  useEffect(() => {
    if (phase === "recording" && streamRef.current && !recorderRef.current) {
      // Fresh recording — clear any pause bookkeeping from a prior run.
      pausedRef.current = false;
      pauseStartRef.current = null;
      pausedAccumRef.current = 0;
      setPaused(false);
      try {
        if (typeof MediaRecorder === "undefined") {
          setRecInfo("MediaRecorder not supported on this browser");
        } else {
          const mime = ["video/webm;codecs=vp9", "video/webm", "video/mp4"].find((m) =>
            MediaRecorder.isTypeSupported?.(m),
          );
          const rec = mime
            ? new MediaRecorder(streamRef.current, { mimeType: mime })
            : new MediaRecorder(streamRef.current);
          chunksRef.current = [];
          rec.ondataavailable = (e) => {
            if (e.data.size) chunksRef.current.push(e.data);
          };
          rec.onerror = () => setRecInfo("recorder error");
          rec.start(1000); // timeslice — iOS Safari is more reliable emitting chunks
          recorderRef.current = rec;
          setRecInfo(`recording (${mime || "default"})`);
        }
      } catch (e) {
        setRecInfo(e instanceof Error ? `recorder failed: ${e.name}` : "recorder failed");
      }
    }
    if (phase === "stopped" && recorderRef.current) {
      const rec = recorderRef.current;
      recorderRef.current = null;
      rec.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || "video/webm" });
        const did = deviceIdRef.current;
        if (!blob.size) {
          setRecInfo("no video data captured");
          return;
        }
        setRecInfo(`uploading ${(blob.size / 1_000_000).toFixed(1)} MB…`);
        try {
          if (did) await api.multicamUpload(sessionId, token, did, blob);
          setUploaded(true);
          setRecInfo(null);
        } catch (e) {
          setRecInfo(e instanceof Error ? `upload failed: ${e.message}` : "upload failed");
        }
      };
      rec.stop();
    }
  }, [phase, sessionId, token]);

  // Post a small preview frame ~1×/s so the coach's live grid shows this camera.
  useEffect(() => {
    if (!["ready", "countdown", "recording"].includes(phase)) return;
    const canvas = document.createElement("canvas");
    const post = async () => {
      const v = videoRef.current;
      const did = deviceIdRef.current;
      if (!v || !did || !v.videoWidth) return;
      const w = 320;
      const h = Math.round((v.videoHeight / v.videoWidth) * w) || 240;
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.drawImage(v, 0, 0, w, h);
      const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", 0.5));
      if (blob) await api.multicamFrame(sessionId, token, did, blob);
    };
    const id = setInterval(post, 1000);
    return () => clearInterval(id);
  }, [phase, sessionId, token]);

  // Load MediaPipe pose once the camera is ready (client-side — the server has no CV).
  useEffect(() => {
    if (phase !== "ready" || landmarkerRef.current || !streamRef.current) return;
    let cancelled = false;
    (async () => {
      try {
        const { PoseLandmarker, FilesetResolver } = await import("@mediapipe/tasks-vision");
        const vision = await FilesetResolver.forVisionTasks(
          "https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision/wasm",
        );
        const lm = await PoseLandmarker.createFromOptions(vision, {
          baseOptions: {
            modelAssetPath:
              "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_full/float16/1/pose_landmarker_full.task",
            delegate: "GPU",
          },
          runningMode: "VIDEO",
          numPoses: 1,
        });
        if (!cancelled) landmarkerRef.current = lm;
      } catch {
        /* model load failed — recording still works, just no live count */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [phase]);

  // Count punches live during recording, using the shared PunchDetector.
  useEffect(() => {
    if (phase !== "recording") return;
    const video = videoRef.current;
    const lm = landmarkerRef.current as {
      detectForVideo: (
        v: HTMLVideoElement,
        t: number,
      ) => {
        landmarks?: { x: number; y: number; z: number; visibility?: number }[][];
        worldLandmarks?: { x: number; y: number; z: number; visibility?: number }[][];
      };
    } | null;
    if (!video || !lm) return;
    detectorRef.current = new PunchDetector(null);
    punchCountRef.current = 0;
    setPunchCount(0);
    poseRef.current = [];
    const startT = performance.now();
    let lastFrame = -1;
    const loop = () => {
      rafRef.current = requestAnimationFrame(loop);
      if (pausedRef.current) return; // frozen while paused — no detection or pose
      if (video.readyState < 2 || video.currentTime === lastFrame) return;
      lastFrame = video.currentTime;
      let res;
      try {
        res = lm.detectForVideo(video, performance.now());
      } catch {
        return;
      }
      const lms = res.landmarks?.[0];
      if (!lms) return;
      const world = res.worldLandmarks?.[0] ?? null;
      const tMs = performance.now() - startT;
      poseRef.current.push({
        t_ms: Math.round(tMs),
        landmarks: lms.map((p) => [p.x, p.y, p.z, p.visibility ?? 1]),
        world_landmarks: world ? world.map((p) => [p.x, p.y, p.z, p.visibility ?? 1]) : null,
      });
      const events = detectorRef.current.feed(lms, world, tMs);
      if (events.length) {
        punchCountRef.current += events.length;
        setPunchCount(punchCountRef.current);
      }
    };
    rafRef.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(rafRef.current);
  }, [phase]);

  // On stop, upload this device's pose stream for offline analysis (per-device parquet).
  useEffect(() => {
    if (phase !== "stopped") return;
    const did = deviceIdRef.current;
    const frames = poseRef.current;
    if (!did || frames.length === 0) return;
    poseRef.current = [];
    api.multicamPose(sessionId, token, did, frames).catch(() => {});
  }, [phase, sessionId, token]);

  const relabel = useCallback(
    async (next: string) => {
      setLabel(next);
      const did = deviceIdRef.current;
      if (did) await api.multicamHeartbeat(sessionId, token, did, "ready").catch(() => {});
    },
    [sessionId, token],
  );

  // Tile mode: just the video filling a grid cell, with a bottom overlay — matches
  // the phone frame-tiles so the laptop sits in the coach's 2×2 grid at the same size.
  if (tile) {
    return (
      <div className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/10 bg-black">
        <video ref={videoRef} autoPlay playsInline muted className="h-full w-full object-cover" />
        {noCamera && (
          <div className="absolute inset-0 grid place-items-center p-2 text-center text-[10px] leading-tight text-neutral-400">
            camera unavailable
          </div>
        )}
        {phase === "countdown" && countdown != null && (
          <div className="absolute inset-0 grid place-items-center bg-black/50">
            <span className="text-5xl font-bold text-white tabular-nums">{countdown}</span>
          </div>
        )}
        {recInfo && (
          <div className="absolute left-1 top-1 max-w-[92%] truncate rounded bg-black/70 px-1.5 py-0.5 text-[10px] text-amber-300">
            {recInfo}
          </div>
        )}
        <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/60 px-2 py-1 text-[11px]">
          <span className="truncate">💻 {label}</span>
          <span className="flex items-center gap-2">
            {(phase === "recording" || phase === "stopped") && punchCount > 0 && (
              <span className="font-semibold text-emerald-400">{punchCount}👊</span>
            )}
            {phase === "recording" ? (
              paused ? (
                <span className="font-semibold text-amber-300">❚❚ paused</span>
              ) : (
                <span className="flex items-center gap-1 font-semibold text-red-300">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-red-500" />
                  {elapsed.toFixed(0)}s
                </span>
              )
            ) : (
              <StatusBadge phase={phase} />
            )}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Camera · {label}</h3>
        <StatusBadge phase={phase} />
      </div>

      <div className="relative overflow-hidden rounded-2xl border border-white/10 bg-black">
        <video
          ref={videoRef}
          autoPlay
          playsInline
          muted
          className="w-full aspect-video object-cover"
        />
        {noCamera && (
          <div className="absolute inset-0 grid place-items-center p-3 text-center text-xs leading-relaxed">
            <span className="text-neutral-400">
              camera unavailable
              <br />
              {camError ? (
                <span className="text-red-400">{camError}</span>
              ) : (
                <span className="text-neutral-500">(sync still active)</span>
              )}
            </span>
          </div>
        )}
        {phase === "countdown" && countdown != null && (
          <div className="absolute inset-0 grid place-items-center bg-black/50">
            <span className="text-7xl font-bold text-white tabular-nums">{countdown}</span>
          </div>
        )}
        {phase === "recording" && (
          <div
            className={`absolute left-3 top-3 flex items-center gap-2 rounded-full px-3 py-1 text-sm font-semibold text-white ${
              paused ? "bg-amber-600/90" : "bg-red-600/90"
            }`}
          >
            {paused ? (
              <>❚❚ PAUSED {elapsed.toFixed(1)}s</>
            ) : (
              <>
                <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-white" /> REC{" "}
                {elapsed.toFixed(1)}s
              </>
            )}
          </div>
        )}
      </div>

      {recInfo && <p className="text-xs text-amber-400">{recInfo}</p>}

      {(phase === "recording" || phase === "stopped") && (
        <p className="text-center text-neutral-300">
          <span className="text-3xl font-bold tabular-nums text-emerald-400">{punchCount}</span>{" "}
          <span className="text-sm">punches</span>
        </p>
      )}

      {phase === "ready" && (
        <div className="space-y-2">
          <p className="text-sm text-neutral-400">
            Connected. Pick an angle, then wait for the coach to start — all cameras start together.
          </p>
          <div className="flex flex-wrap gap-2">
            {LABELS.map((l) => (
              <button
                key={l}
                onClick={() => relabel(l)}
                className={`rounded-lg border px-3 py-1 text-xs ${
                  l === label
                    ? "border-emerald-400 bg-emerald-500/20 text-emerald-300"
                    : "border-white/10 text-neutral-400 hover:bg-white/5"
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </div>
      )}
      {phase === "stopped" && (
        <p className="text-sm text-neutral-400">
          {uploaded ? "✓ Clip uploaded. " : ""}Session stopped.
        </p>
      )}
      {phase === "error" && <p className="text-sm text-red-400">{err}</p>}
    </div>
  );
}

function StatusBadge({ phase }: { phase: Phase }) {
  const map: Record<Phase, [string, string]> = {
    connecting: ["Connecting…", "bg-neutral-500"],
    ready: ["Ready", "bg-emerald-500"],
    countdown: ["Starting…", "bg-amber-500"],
    recording: ["Recording", "bg-red-500"],
    stopped: ["Stopped", "bg-neutral-500"],
    error: ["Error", "bg-red-500"],
  };
  const [text, color] = map[phase];
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-neutral-300">
      <span className={`h-2 w-2 rounded-full ${color}`} /> {text}
    </span>
  );
}

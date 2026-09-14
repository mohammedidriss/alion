"use client";

/**
 * Multi-camera device panel (ADR-010) — the master/coach view. Shows a live grid
 * of every connected phone camera (≈1 fps preview frames each posts), the laptop as
 * its own single camera screen, the round timer, and one synchronized Start/Stop.
 * The join QR lives in <JoinQrCard> under the round-configuration panel.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { CameraNode } from "@/components/CameraNode";
import { RoundTimer } from "@/components/SessionRounds";
import { api, type MulticamDevice, type Session } from "@/lib/api";

export function MulticamPanel({
  session,
  defaultLaptop = false,
}: {
  session: Session;
  defaultLaptop?: boolean;
}) {
  const sessionId = session.id;
  const [token, setToken] = useState<string | null>(null);
  const [devices, setDevices] = useState<MulticamDevice[]>([]);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [laptopOn, setLaptopOn] = useState(defaultLaptop);
  const [laptopDeviceId, setLaptopDeviceId] = useState<string | null>(null);
  const [captureStartMs, setCaptureStartMs] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  const pausedAccumRef = useRef(0); // total paused ms, subtracted from timer elapsed
  const pauseStartRef = useRef<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .multicamJoinInfo(sessionId)
      .then((ji) => setToken(ji.join_token))
      .catch(() => setMsg("Could not connect cameras to this session."));
  }, [sessionId]);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .multicamDevices(sessionId)
        .then((d) => alive && setDevices(d))
        .catch(() => {});
    const id = setInterval(poll, 1500);
    poll();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId]);

  // Refresh the live-grid frames ~1×/s.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const start = useCallback(async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.multicamStart(sessionId);
      pausedAccumRef.current = 0;
      pauseStartRef.current = null;
      setPaused(false);
      setCaptureStartMs(Date.now());
      setMsg(`Recording ${r.devices} camera(s) together…`);
    } catch {
      setMsg("Connect at least one camera first.");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  const pause = useCallback(async () => {
    await api.multicamPause(sessionId).catch(() => {});
    pauseStartRef.current = Date.now();
    setPaused(true);
    setMsg("Paused — press Resume to continue the same clip.");
  }, [sessionId]);

  const resume = useCallback(async () => {
    await api.multicamResume(sessionId).catch(() => {});
    if (pauseStartRef.current != null) {
      pausedAccumRef.current += Date.now() - pauseStartRef.current;
      pauseStartRef.current = null;
    }
    setPaused(false);
    setMsg("Recording…");
  }, [sessionId]);

  const stop = useCallback(async () => {
    await api.multicamStop(sessionId).catch(() => {});
    setCaptureStartMs(null);
    setPaused(false);
    pauseStartRef.current = null;
    pausedAccumRef.current = 0;
    setMsg("Match ended — clips saved. See “Camera recordings” below.");
  }, [sessionId]);

  const allCams = devices.filter((d) => d.role === "camera");
  // The laptop shows as its own <CameraNode> below, so keep it out of the grid —
  // but still count it toward the connected total and the consensus punch count.
  const cams = allCams.filter((d) => d.device_id !== laptopDeviceId);
  const maxPunches = allCams.reduce((m, c) => Math.max(m, c.punches), 0);
  const canStart = allCams.length > 0 || laptopOn;
  const capturing = captureStartMs !== null;
  const activeMs = capturing
    ? Math.max(
        0,
        Date.now() -
          captureStartMs -
          pausedAccumRef.current -
          (pauseStartRef.current != null ? Date.now() - pauseStartRef.current : 0),
      )
    : 0;

  return (
    <div className="rounded-2xl border border-white/10 p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Cameras</h3>
        <span className="text-xs text-neutral-500">
          {allCams.length} connected
          {maxPunches > 0 && <span className="text-emerald-400"> · ~{maxPunches} punches</span>}
        </span>
      </div>

      {/* Controls above the grid: Start → Pause/Resume + Stop (Stop ends & saves). */}
      <div className="flex flex-wrap items-center gap-2">
        {!capturing ? (
          <button
            onClick={start}
            disabled={busy || !canStart}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
          >
            Start all cameras
          </button>
        ) : (
          <>
            {paused ? (
              <button
                onClick={resume}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400"
              >
                ▶ Resume
              </button>
            ) : (
              <button
                onClick={pause}
                className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-semibold text-black hover:bg-amber-400"
              >
                ❚❚ Pause
              </button>
            )}
            <button
              onClick={stop}
              className="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500"
            >
              ■ Stop &amp; save
            </button>
          </>
        )}
        {msg && <span className="text-xs text-neutral-400">{msg}</span>}
      </div>

      {/* Round timer — runs off the round-configuration panel (round_count ×
          round_duration_s); paused time is subtracted so it freezes on Pause. */}
      {capturing && <RoundTimer session={session} durationMs={activeMs} isPaused={paused} />}

      {/* Fixed 2×2 grid: top-left is always the laptop; the other three are phones. */}
      <div className="grid grid-cols-2 gap-2">
        {/* Slot 0 — laptop (always top-left) */}
        {laptopOn && token ? (
          <div className="relative">
            <CameraNode
              sessionId={sessionId}
              token={token}
              defaultLabel="laptop"
              tile
              onDeviceId={setLaptopDeviceId}
            />
            <button
              onClick={() => {
                setLaptopOn(false);
                setLaptopDeviceId(null);
              }}
              className="absolute right-1 top-1 rounded bg-black/70 px-1.5 py-0.5 text-[10px] text-neutral-300 hover:text-white"
            >
              Disable
            </button>
          </div>
        ) : (
          <button
            onClick={() => setLaptopOn(true)}
            className="flex aspect-video w-full flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-white/15 text-xs text-neutral-400 hover:bg-white/5"
          >
            <span className="text-lg">💻</span>
            Enable laptop camera
          </button>
        )}

        {/* Slots 1–3 — phone cameras, or empty placeholders */}
        {[0, 1, 2].map((i) => {
          const d = cams[i];
          if (d && token) {
            return (
              <div
                key={d.device_id}
                className="relative aspect-video w-full overflow-hidden rounded-xl border border-white/10 bg-black"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={`${api.multicamFrameUrl(sessionId, token, d.device_id)}&t=${tick}`}
                  alt={d.label}
                  className="h-full w-full object-cover"
                  onError={(e) => {
                    (e.currentTarget as HTMLImageElement).style.visibility = "hidden";
                  }}
                  onLoad={(e) => {
                    (e.currentTarget as HTMLImageElement).style.visibility = "visible";
                  }}
                />
                <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/60 px-2 py-1 text-[11px]">
                  <span className="truncate">📷 {d.label}</span>
                  <span className="flex items-center gap-2">
                    {d.punches > 0 && (
                      <span className="font-semibold text-emerald-400">{d.punches}👊</span>
                    )}
                    <StatusDot status={d.status} />
                  </span>
                </div>
              </div>
            );
          }
          return (
            <div
              key={`empty-${i}`}
              className="flex aspect-video w-full flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-white/10 text-[11px] text-neutral-500"
            >
              <span className="text-base">📷</span>
              Scan QR to add
            </div>
          );
        })}
      </div>

      {cams.length > 3 && (
        <p className="text-xs text-neutral-500">
          +{cams.length - 3} more camera(s) connected (grid shows 4).
        </p>
      )}
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "recording" ? "bg-red-500" : status === "ready" ? "bg-emerald-500" : "bg-neutral-500";
  return (
    <span className="inline-flex items-center gap-1 text-neutral-300">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {status}
    </span>
  );
}

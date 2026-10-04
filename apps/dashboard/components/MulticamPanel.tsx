"use client";

/**
 * Multi-camera device panel (ADR-010) — the master/coach view. Shows a live grid
 * of every connected phone camera (≈1 fps preview frames each posts), the laptop as
 * its own single camera screen, the round timer, and one synchronized Start/Stop.
 * The join QR lives in <JoinQrCard> (top middle of the session page header).
 *
 * The body sensors ride along. The wrist IMUs, if the pair belongs to this
 * session's fighter, start right after the cameras (t = 0 is the cameras'
 * synchronized start) and stop with them; Pause/Resume reach them server-side via
 * the coordinator. A paired Polar H10 streams heart rate for the same span.
 *
 * Dataset takes (ADR-013) use the same panel with `take` instead of `session`:
 * everything records into the take's folder, there's no Pause (labels need an
 * unbroken timeline) and an elapsed timer replaces the round timer.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CameraNode } from "@/components/CameraNode";
import { imuErrorText } from "@/components/ImuSensors";
import { getPairedDevice } from "@/components/PolarH10Card";
import { RoundTimer } from "@/components/SessionRounds";
import { api, type CaptureRef, type MulticamDevice, type Session, type Take } from "@/lib/api";

export function MulticamPanel({
  session,
  take,
  defaultLaptop = false,
  onFinished,
}: {
  session?: Session;
  take?: Take; // a dataset take instead of a session
  defaultLaptop?: boolean;
  /** Called once Stop has saved the clips and completed the session / take. */
  onFinished?: () => void;
}) {
  const sessionId = session?.id;
  const takeId = take?.id;
  const fighterId = session?.fighter_id ?? take?.fighter_id ?? "";
  const cap = useMemo<CaptureRef>(
    () => (takeId ? { kind: "take", id: takeId } : (sessionId ?? "")),
    [takeId, sessionId],
  );
  const [token, setToken] = useState<string | null>(null);
  const [devices, setDevices] = useState<MulticamDevice[]>([]);
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState(false);
  const [laptopOn, setLaptopOn] = useState(defaultLaptop);
  const [laptopDeviceId, setLaptopDeviceId] = useState<string | null>(null);
  const [captureStartMs, setCaptureStartMs] = useState<number | null>(null);
  const [paused, setPaused] = useState(false);
  const [stopping, setStopping] = useState(false);
  const pausedAccumRef = useRef(0); // total paused ms, subtracted from timer elapsed
  const pauseStartRef = useRef<number | null>(null);
  const devicesRef = useRef<MulticamDevice[]>([]);
  const activeMsRef = useRef(0);
  const [msg, setMsg] = useState<string | null>(null);
  const [imuMsg, setImuMsg] = useState<string | null>(null);
  const [imuMine, setImuMine] = useState(false); // the IMU pair belongs to this fighter

  useEffect(() => {
    api
      .imuDevices()
      .then((d) => setImuMine(d.units.length > 0 && d.owner?.fighter_id === fighterId))
      .catch(() => setImuMine(false));
  }, [fighterId]);

  useEffect(() => {
    api
      .multicamJoinInfo(cap)
      .then((ji) => setToken(ji.join_token))
      .catch(() => setMsg("Could not connect cameras."));
  }, [cap]);

  useEffect(() => {
    let alive = true;
    const poll = () =>
      api
        .multicamDevices(cap)
        .then((d) => alive && setDevices(d))
        .catch(() => {});
    const id = setInterval(poll, 1500);
    poll();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [cap]);

  // Refresh the live-grid frames ~1×/s.
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const start = useCallback(async () => {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api.multicamStart(cap);
      pausedAccumRef.current = 0;
      pauseStartRef.current = null;
      setPaused(false);
      setCaptureStartMs(Date.now());
      setMsg(`Recording ${r.devices} camera(s) together…`);
    } catch {
      setMsg("Connect at least one camera first.");
      setBusy(false);
      return;
    }
    setImuMsg(null);
    const problems: string[] = [];
    const polar = getPairedDevice();
    await Promise.all([
      // After multicamStart, so the IMU's t = 0 is the cameras' scheduled start.
      imuMine &&
        api
          .startImuBle(cap)
          .catch((e) => problems.push(`Wrist sensors didn't start: ${imuErrorText(e)}`)),
      polar &&
        api
          .startHrvBle(cap, polar.address)
          .catch((e) => problems.push(`Heart-rate strap didn't start: ${imuErrorText(e)}`)),
    ]);
    if (problems.length) setImuMsg(problems.join(" "));
    setBusy(false);
  }, [cap, imuMine]);

  const pause = useCallback(async () => {
    await api.multicamPause(cap).catch(() => {});
    pauseStartRef.current = Date.now();
    setPaused(true);
    setMsg("Paused — press Resume to continue the same clip.");
  }, [cap]);

  const resume = useCallback(async () => {
    await api.multicamResume(cap).catch(() => {});
    if (pauseStartRef.current != null) {
      pausedAccumRef.current += Date.now() - pauseStartRef.current;
      pauseStartRef.current = null;
    }
    setPaused(false);
    setMsg("Recording…");
  }, [cap]);

  // Stop & save: end the recording everywhere, wait for each camera's clip to land,
  // then complete the session (which swaps this panel for the recordings view).
  const stop = useCallback(async () => {
    if (stopping) return;
    setStopping(true);
    setMsg("Stopping — saving clips…");
    const durationMs = activeMsRef.current;
    // Cameras recording right now each upload one clip after the stop command.
    const recording = devicesRef.current.filter(
      (d) => d.role === "camera" && (d.status === "recording" || d.status === "paused"),
    ).length;
    const expected = Math.max(1, recording);
    const before = new Map(
      (await api.multicamClips(cap).catch(() => [])).map((c) => [c.device_id, c.bytes]),
    );
    await api.multicamStop(cap).catch(() => {});
    setCaptureStartMs(null);
    setPaused(false);
    pauseStartRef.current = null;
    pausedAccumRef.current = 0;
    // Body sensors shut down in the background — a wrist unit that's off can take
    // seconds to give up connecting, and the clips shouldn't wait on it.
    void api.stopImuBle(cap).catch(() => {});
    void api.stopHrv(cap).catch(() => {});

    // A clip is "new" if its device had none before, or its file changed (a re-take
    // overwrites the same device's file). Nodes upload on their next heartbeat.
    let fresh = 0;
    for (let i = 0; i < 40; i++) {
      const clips = await api.multicamClips(cap).catch(() => []);
      fresh = clips.filter((c) => before.get(c.device_id) !== c.bytes).length;
      if (fresh >= expected) break;
      setMsg(`Stopping — saving clips… (${fresh}/${expected})`);
      await new Promise((r) => setTimeout(r, 750));
    }
    if (fresh === 0) {
      setStopping(false);
      setMsg("No video was saved — the cameras didn't record anything.");
      return;
    }
    try {
      await api.multicamComplete(cap, durationMs);
      setMsg(`Saved ${fresh} clip(s).`);
      onFinished?.();
    } catch {
      setMsg(`Saved ${fresh} clip(s), but the session couldn't be marked complete.`);
    } finally {
      setStopping(false);
    }
  }, [cap, stopping, onFinished]);

  const allCams = devices.filter((d) => d.role === "camera");
  devicesRef.current = devices;
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
  activeMsRef.current = activeMs;

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
            disabled={busy || stopping || !canStart}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
          >
            Start all cameras
          </button>
        ) : (
          <>
            {take ? null : paused ? (
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
              disabled={stopping}
              className="rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white hover:bg-red-500 disabled:cursor-wait disabled:opacity-60"
            >
              {stopping ? "Saving…" : "■ Stop & save"}
            </button>
          </>
        )}
        {msg && <span className="text-xs text-neutral-400">{msg}</span>}
        {imuMsg && <span className="text-xs text-red-300">{imuMsg}</span>}
      </div>

      {/* Round timer — runs off the round-configuration panel (round_count ×
          round_duration_s); paused time is subtracted so it freezes on Pause. */}
      {capturing && session && (
        <RoundTimer session={session} durationMs={activeMs} isPaused={paused} />
      )}
      {/* Takes: a plain elapsed clock (the protocol card paces the blocks). */}
      {capturing && take && (
        <div className="flex items-center gap-2 font-mono text-2xl tabular-nums">
          <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />
          {Math.floor(activeMs / 60000)}:{String(Math.floor(activeMs / 1000) % 60).padStart(2, "0")}
        </div>
      )}

      {/* Fixed 2×2 grid: top-left is always the laptop; the other three are phones. */}
      <div className="grid grid-cols-2 gap-2">
        {/* Slot 0 — laptop (always top-left) */}
        {laptopOn && token ? (
          <div className="relative">
            <CameraNode
              sessionId={sessionId}
              takeId={takeId}
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
                  src={`${api.multicamFrameUrl(cap, token, d.device_id)}&t=${tick}`}
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

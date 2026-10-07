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
import { say, unlockCues } from "@/lib/cues";

export function MulticamPanel({
  session,
  take,
  defaultLaptop = false,
  stopSignal = 0,
  onStopping,
  onFinished,
  onDelete,
}: {
  session?: Session;
  take?: Take; // a dataset take instead of a session
  defaultLaptop?: boolean;
  /** Bump to Stop & save (the block's last beep has passed). */
  stopSignal?: number;
  /** Called as soon as Stop is sent — the cameras are now uploading their video. */
  onStopping?: () => void;
  /** Called once Stop has saved the clips and completed the session / take. */
  onFinished?: () => void;
  /** "Delete": the page deletes this recording (and opens a fresh one). The panel
   *  has already told the cameras to drop their clips. */
  onDelete?: () => Promise<void>;
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
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
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

  // Pre-connect the body sensors as soon as the page is open, so Bluetooth is done
  // before Start: the wrists (and, on a take, the Polar) stream live but store
  // nothing until the cameras' t = 0, then everything records together.
  const [sensors, setSensors] = useState<{ l: boolean | null; r: boolean | null; hr: boolean | null }>({
    l: null,
    r: null,
    hr: null,
  });
  useEffect(() => {
    if (captureStartMs !== null || stopping || deleting) return;
    const polar = getPairedDevice();
    if (imuMine) api.startImuBle(cap, { arm: true }).catch(() => {});
    if (take && polar) api.startHrvBle(cap, polar.address).catch(() => {});
    let alive = true;
    const poll = async () => {
      const r = await api.liveReading(cap).catch(() => null);
      if (!alive || !r) return;
      setSensors({
        l: imuMine ? !!r.imu.units.left?.connected : null,
        r: imuMine ? !!r.imu.units.right?.connected : null,
        hr: polar ? r.heart.bpm_trace.length > 0 || r.heart.streaming : null,
      });
    };
    poll();
    const id = setInterval(poll, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cap, imuMine, captureStartMs === null, stopping, deleting]);

  // While recording, bring back a sensor stream that died — e.g. the API restarted
  // (it reloads on every code save), which ends the wrist recorder and the Polar
  // thread. They rejoin on the same timeline: t = 0 stays the cameras' start.
  useEffect(() => {
    if (captureStartMs === null || stopping) return;
    const id = setInterval(async () => {
      const r = await api.liveReading(cap).catch(() => null);
      if (!r) return;
      if (imuMine && !r.imu.running) api.startImuBle(cap).catch(() => {});
      const polar = getPairedDevice();
      if (polar && !r.heart.streaming) api.startHrvBle(cap, polar.address).catch(() => {});
    }, 10_000);
    return () => clearInterval(id);
  }, [captureStartMs, stopping, cap, imuMine]);

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

  /** Wait for the cameras' clips, then complete. A clip is "new" if its device had
   *  none before, or its file changed (a re-take overwrites the same device's file);
   *  it only shows up once fully uploaded. Waits while any camera is still recording
   *  or uploading (up to 15 min) — `idleMs` after the last one goes quiet, it saves
   *  what arrived (a camera that left doesn't hold the take hostage). */
  const finishSave = useCallback(
    async (before: Map<string, number>, expected: number, durationMs?: number, idleMs = 20_000) => {
      let fresh = 0;
      let idleSince: number | null = null;
      const deadline = Date.now() + 15 * 60_000;
      while (Date.now() < deadline) {
        const clips = await api.multicamClips(cap).catch(() => []);
        fresh = clips.filter((c) => before.get(c.device_id) !== c.bytes).length;
        if (fresh >= expected) break;
        const roster = await api.multicamDevices(cap).catch(() => null);
        const busy = roster
          ? roster.some(
              (d) =>
                d.role === "camera" &&
                (d.status === "uploading" || d.status === "recording" || d.status === "paused"),
            )
          : true;
        idleSince = busy ? null : (idleSince ?? Date.now());
        if (idleSince !== null && Date.now() - idleSince > idleMs) break;
        setMsg(
          Number.isFinite(expected)
            ? `Uploading video — ${fresh} of ${expected} camera${expected === 1 ? "" : "s"} done. ` +
                "Keep this page and the phones open."
            : `Uploading video — ${fresh} camera${fresh === 1 ? "" : "s"} done so far. Keep the phones open.`,
        );
        await new Promise((r) => setTimeout(r, 1000));
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
    },
    [cap, onFinished],
  );

  // Stop & save: end the recording everywhere, wait for each camera's clip to land,
  // then complete the session (which swaps this panel for the recordings view). A
  // long take's clip is a few hundred MB, so this waits as long as the cameras are
  // still uploading; a clip only shows up once all of it has arrived.
  const resumed = useRef(false); // this panel has saved (or is saving) already
  const stop = useCallback(async () => {
    if (stopping) return;
    resumed.current = true;
    setStopping(true);
    setMsg("Stopping — the cameras are uploading their video…");
    const durationMs = activeMsRef.current;
    // Cameras recording right now each upload one clip after the stop command.
    const recording = devicesRef.current.filter(
      (d) =>
        d.role === "camera" &&
        (d.status === "recording" || d.status === "paused" || d.status === "hidden"),
    ).length;
    const expected = Math.max(1, recording);
    const before = new Map(
      (await api.multicamClips(cap).catch(() => [])).map((c) => [c.device_id, c.bytes]),
    );
    await api.multicamStop(cap).catch(() => {});
    onStopping?.();
    setCaptureStartMs(null);
    setPaused(false);
    pauseStartRef.current = null;
    pausedAccumRef.current = 0;
    // Body sensors shut down in the background — a wrist unit that's off can take
    // seconds to give up connecting, and the clips shouldn't wait on it.
    void api.stopImuBle(cap).catch(() => {});
    void api.stopHrv(cap).catch(() => {});

    await finishSave(before, expected, durationMs);
  }, [cap, stopping, onStopping, finishSave]);

  // Reopened while the cameras were still uploading (page reloaded after Stop):
  // pick the save back up — wait for the uploads, then complete the take.
  useEffect(() => {
    if (take?.status !== "uploading" || resumed.current || stopping) return;
    resumed.current = true;
    setStopping(true);
    setMsg("Uploading video — finishing the save…");
    void finishSave(new Map(), Infinity, undefined, 5_000);
  }, [take?.status, stopping, finishSave]);

  const lastStop = useRef(stopSignal);
  useEffect(() => {
    if (stopSignal === lastStop.current) return;
    lastStop.current = stopSignal;
    if (captureStartMs !== null) void stop();
  }, [stopSignal, captureStartMs, stop]);

  // Delete: a two-step button (it can't be undone); the confirm lapses after 6 s.
  useEffect(() => {
    if (!confirmDelete) return;
    const id = setTimeout(() => setConfirmDelete(false), 6000);
    return () => clearTimeout(id);
  }, [confirmDelete]);

  const deleteRecording = useCallback(async () => {
    if (!onDelete || deleting) return;
    setDeleting(true);
    setConfirmDelete(false);
    setMsg("Deleting the recording…");
    await api.multicamDiscard(cap).catch(() => {}); // cameras drop their clips
    void api.stopImuBle(cap).catch(() => {});
    void api.stopHrv(cap).catch(() => {});
    setCaptureStartMs(null);
    setPaused(false);
    pauseStartRef.current = null;
    pausedAccumRef.current = 0;
    try {
      await onDelete();
    } catch (e) {
      setMsg(`Couldn't delete: ${imuErrorText(e)}`);
      setDeleting(false);
    }
  }, [cap, onDelete, deleting]);

  const allCams = devices.filter((d) => d.role === "camera");
  devicesRef.current = devices;
  // The laptop shows as its own <CameraNode> below, so keep it out of the grid —
  // but still count it toward the connected total and the consensus punch count.
  const cams = allCams.filter((d) => d.device_id !== laptopDeviceId);
  const maxPunches = allCams.reduce((m, c) => Math.max(m, c.punches), 0);
  const canStart = allCams.length > 0 || laptopOn;
  // Cameras whose pose isn't ready yet, or whose page is off screen while recording.
  const loadingCams = devices.filter((d) => d.role === "camera" && d.status === "loading");
  const hiddenCams = devices.filter((d) => d.role === "camera" && d.status === "hidden");
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
            {onDelete &&
              (confirmDelete ? (
                <span className="flex items-center gap-1.5 rounded-xl border border-red-500/40 bg-red-950/40 px-2 py-1 text-xs">
                  <span className="text-red-200">Delete this recording?</span>
                  <button
                    onClick={deleteRecording}
                    className="rounded-lg bg-red-600 px-2.5 py-1 font-semibold text-white hover:bg-red-500"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => setConfirmDelete(false)}
                    className="rounded-lg px-2 py-1 text-neutral-300 hover:bg-white/10"
                  >
                    Keep recording
                  </button>
                </span>
              ) : (
                <button
                  onClick={() => setConfirmDelete(true)}
                  disabled={stopping || deleting}
                  title="Throw this recording away (nothing is saved) and start a fresh one"
                  className="rounded-xl border border-red-500/50 px-4 py-2 text-sm font-semibold text-red-300 hover:bg-red-500/10 disabled:opacity-40"
                >
                  {deleting ? "Deleting…" : "🗑 Delete"}
                </button>
              ))}
          </>
        )}
        {msg && <span className="text-xs text-neutral-400">{msg}</span>}
        {captureStartMs === null && loadingCams.length > 0 && (
          <span className="text-xs text-amber-300">
            {loadingCams.map((d) => d.label).join(", ")}: pose model still loading — wait for it to
            turn green before Start, or that camera records without pose.
          </span>
        )}
        {captureStartMs !== null && hiddenCams.length > 0 && (
          <span className="text-xs text-amber-300">
            {hiddenCams.map((d) => d.label).join(", ")}: page off screen — its video keeps recording
            but pose stopped. Bring it to the front.
          </span>
        )}
        {imuMsg && <span className="text-xs text-red-300">{imuMsg}</span>}
      </div>

      {/* Body sensors connect before Start, so they record from the same t = 0. */}
      {!capturing && (sensors.l !== null || sensors.hr !== null) && (
        <div className="flex flex-wrap items-center gap-3 text-xs text-neutral-400">
          <span>Ready to record together:</span>
          {sensors.l !== null && <SensorDot label="Left wrist" ok={sensors.l} />}
          {sensors.r !== null && <SensorDot label="Right wrist" ok={sensors.r} />}
          {sensors.hr !== null && <SensorDot label="Heart rate" ok={sensors.hr} />}
          {sensors.l && sensors.r && <WristCheck cap={cap} />}
        </div>
      )}

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
                  className="h-full w-full object-contain"
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

/**
 * "Which wrist?" — the two WT901 units look identical and get strapped on the
 * wrong wrists, which flips every label. With the sensors pre-connected, ask the
 * fighter to shake the LEFT hand and see which unit moved; if it's the one
 * assigned to the right, offer to swap the assignment (no re-strapping).
 */
function WristCheck({ cap }: { cap: CaptureRef }) {
  type State = "idle" | "shaking" | "ok" | "swapped" | "unclear" | "fixing";
  const [state, setState] = useState<State>("idle");

  const run = async () => {
    unlockCues();
    setState("shaking");
    say("Shake your left hand now.");
    await new Promise((r) => setTimeout(r, 3500));
    const r = await api.liveReading(cap).catch(() => null);
    // Movement over the last ~3 s: the biggest |a| − 1 g in each wrist's live trace.
    const moved = (h: "left" | "right") =>
      Math.max(0, ...(r?.imu.units[h]?.trace ?? []).slice(-60).map((g) => Math.abs(g - 1)));
    const l = moved("left");
    const rt = moved("right");
    if (Math.max(l, rt) < 0.5) setState("unclear");
    else if (l > rt * 1.5) setState("ok");
    else if (rt > l * 1.5) setState("swapped");
    else setState("unclear");
  };

  const fix = async () => {
    setState("fixing");
    await api.swapImuWrists().catch(() => {});
    // Reconnect so the stream labels its samples with the new wrists.
    await api.stopImuBle(cap).catch(() => {});
    await api.startImuBle(cap, { arm: true }).catch(() => {});
    setState("idle");
  };

  if (state === "shaking")
    return <span className="font-semibold text-amber-200">Shake your LEFT hand…</span>;
  if (state === "ok") return <span className="text-emerald-300">✓ Left sensor is on your left wrist</span>;
  if (state === "swapped")
    return (
      <span className="flex items-center gap-2 text-red-300">
        The sensors are on the opposite wrists.
        <button
          onClick={fix}
          className="rounded-lg bg-red-600 px-2 py-0.5 font-semibold text-white hover:bg-red-500"
        >
          Fix: swap left and right
        </button>
      </span>
    );
  if (state === "fixing") return <span className="text-neutral-400">Swapping and reconnecting…</span>;
  return (
    <button
      onClick={run}
      className="rounded-lg border border-white/15 px-2 py-0.5 text-neutral-300 hover:bg-white/5"
      title="Shake your left hand when asked — catches sensors strapped on the wrong wrists"
    >
      {state === "unclear" ? "Couldn't tell — check again" : "Check which wrist is which"}
    </button>
  );
}

function SensorDot({ label, ok }: { label: string; ok: boolean }) {
  return (
    <span className={`flex items-center gap-1 ${ok ? "text-emerald-300" : "text-amber-300"}`}>
      <span className={`h-2 w-2 rounded-full ${ok ? "bg-emerald-500" : "animate-pulse bg-amber-500"}`} />
      {label} {ok ? "connected" : "connecting…"}
    </span>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "recording"
      ? "bg-red-500"
      : status === "uploading"
        ? "animate-pulse bg-sky-400"
        : status === "ready"
          ? "bg-emerald-500"
          : status === "loading"
            ? "animate-pulse bg-amber-400"
            : status === "hidden"
              ? "bg-amber-500"
              : "bg-neutral-500";
  const text =
    status === "loading" ? "loading pose" : status === "hidden" ? "off screen — no pose" : status;
  return (
    <span className="inline-flex items-center gap-1 text-neutral-300">
      <span className={`h-2 w-2 rounded-full ${color}`} />
      {text}
    </span>
  );
}

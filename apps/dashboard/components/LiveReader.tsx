"use client";

/**
 * Live reader — a smartwatch-style readout for the running session: a heart that
 * beats at the fighter's real rate (Polar H10), the HR zone and HRV, and a rolling
 * 5-second g trace per wrist (WT901 IMUs). One poll (`/v2/sessions/{id}/live`)
 * twice a second while anything streams, every 2 s while idle.
 */

import { useEffect, useState } from "react";
import { type CaptureRef, type ImuHand, type ImuUnitStatus, type LiveReading, api } from "@/lib/api";
import { getPairedDevice } from "@/components/PolarH10Card";
import { useAuth } from "@/lib/auth";

const ZONES = [
  { name: "Rest", color: "#737373" },
  { name: "Warm-up", color: "#94a3b8" },
  { name: "Easy", color: "#38bdf8" },
  { name: "Aerobic", color: "#22c55e" },
  { name: "Threshold", color: "#f59e0b" },
  { name: "Max", color: "#ef4444" },
];

const WRIST_COLOR: Record<ImuHand, string> = {
  left: "rgb(56, 189, 248)",
  right: "rgb(34, 197, 94)",
};

export function LiveReader({
  sessionId,
  takeId,
  fighterId,
}: {
  sessionId?: string;
  takeId?: string; // a dataset take instead of a session (ADR-013)
  fighterId: string;
}) {
  const { user } = useAuth();
  const [reading, setReading] = useState<LiveReading | null>(null);
  const [imuMine, setImuMine] = useState(false);
  const [strapPaired, setStrapPaired] = useState(false);

  useEffect(() => {
    setStrapPaired(getPairedDevice() !== null);
    api
      .imuDevices()
      .then((d) => setImuMine(d.units.length > 0 && d.owner?.fighter_id === fighterId))
      .catch(() => setImuMine(false));
  }, [fighterId]);

  useEffect(() => {
    const cap: CaptureRef = takeId ? { kind: "take", id: takeId } : (sessionId ?? "");
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      const r = await api.liveReading(cap).catch(() => null);
      if (!alive) return;
      if (r) setReading(r);
      const streaming = !!r && (r.heart.streaming || r.imu.running);
      timer = setTimeout(poll, streaming ? 500 : 2000);
    };
    poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [sessionId, takeId]);

  // HRV is confidential biometric data — admins don't see it (same rule as the HRV tab).
  const showHeart = user?.role !== "admin";
  const heart = reading?.heart;
  const imu = reading?.imu;
  const live = !!heart?.streaming || !!imu?.running;

  return (
    <div className="rounded-3xl border border-white/10 bg-black p-4 shadow-[0_0_0_4px_rgba(255,255,255,0.03)]">
      <div className="flex items-center justify-between text-[10px] font-semibold uppercase tracking-widest">
        <span className="text-neutral-500">Live</span>
        {live ? (
          <span className="flex items-center gap-1 text-red-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
            {imu?.paused ? "paused" : "on"}
          </span>
        ) : (
          <span className="text-neutral-600">idle</span>
        )}
      </div>

      {showHeart && (
        <HeartFace
          streaming={!!heart?.streaming}
          bpm={heart?.bpm ?? null}
          trace={heart?.bpm_trace ?? []}
          rmssd={heart?.rmssd_ms ?? null}
          zone={heart?.zone ?? null}
          maxHr={heart?.max_hr ?? null}
          idleText={
            heart?.error
              ? `Polar: ${heartErrorText(heart.error)}`
              : !strapPaired
                ? "Pair the Polar H10 (Scan, above) to see heart rate"
                : imu?.running
                  ? "Strap paired but not sending — wear it with damp contacts and close the Polar app"
                  : "Polar H10 starts with the cameras"
          }
        />
      )}

      <div className={showHeart ? "mt-3 border-t border-white/10 pt-3" : "mt-2"}>
        {imuMine ? (
          <div className="space-y-2">
            {(["left", "right"] as ImuHand[]).map((hand) => (
              <WristRow key={hand} hand={hand} unit={imu?.units[hand]} running={!!imu?.running} />
            ))}
            {!imu?.running && (
              <p className="text-center text-[10px] text-neutral-600">
                Wrist sensors start with the cameras
              </p>
            )}
            {imu?.error && <p className="text-[10px] text-red-400">{imu.error}</p>}
            {imu?.running &&
              (["left", "right"] as ImuHand[]).map((hand) => {
                const u = imu.units[hand];
                return u && !u.connected && u.error ? (
                  <p key={hand} className="text-[10px] leading-snug text-red-400">
                    {hand === "left" ? "Left" : "Right"} wrist: {wristErrorText(u.error)}
                  </p>
                ) : null;
              })}
          </div>
        ) : (
          <p className="text-center text-[10px] text-neutral-600">No wrist sensors on this fighter</p>
        )}
      </div>
    </div>
  );
}

/** The recorder's BLE error in words: "not found" usually means the unit is off,
 *  out of range, or still connected to another capture. */
function heartErrorText(err: string): string {
  if (/not found|no device/i.test(err))
    return "strap not found — wear it with damp contacts, and close the Polar app on your phone.";
  return err;
}

function wristErrorText(err: string): string {
  if (/not found/i.test(err))
    return "not found — is it switched on and nearby? Another take may still hold it; starting this one takes it over within a few seconds.";
  if (/timeout|timed out/i.test(err)) return "connection timed out — move it closer to the laptop.";
  return err;
}

function HeartFace({
  streaming,
  bpm,
  trace,
  rmssd,
  zone,
  maxHr,
  idleText,
}: {
  streaming: boolean;
  bpm: number | null;
  trace: number[];
  rmssd: number | null;
  zone: number | null;
  maxHr: number | null;
  idleText: string;
}) {
  const beating = streaming && bpm != null && bpm > 20;
  const z = zone != null ? ZONES[zone] : null;
  return (
    <div className="mt-2">
      <div className="flex items-center gap-3">
        <svg
          viewBox="0 0 24 24"
          className={`h-10 w-10 shrink-0 ${beating ? "alion-heartbeat" : ""}`}
          style={beating ? { animationDuration: `${(60 / bpm!).toFixed(3)}s` } : undefined}
          aria-hidden
        >
          <path
            d="M12 21s-7.5-4.6-9.6-9.3C.9 8.4 3 4.5 6.7 4.5c2.1 0 3.6 1.2 4.3 2.4h2c.7-1.2 2.2-2.4 4.3-2.4 3.7 0 5.8 3.9 4.3 7.2C19.5 16.4 12 21 12 21z"
            fill={beating ? "#ef4444" : "#404040"}
          />
        </svg>
        <div className="min-w-0">
          <div className="flex items-baseline gap-1">
            <span
              className="text-4xl font-bold tabular-nums leading-none"
              style={{ color: beating ? (z?.color ?? "#fafafa") : "#525252" }}
            >
              {bpm != null ? Math.round(bpm) : "--"}
            </span>
            <span className="text-xs font-medium text-neutral-500">BPM</span>
          </div>
          <div className="mt-1 truncate text-[11px] text-neutral-400">
            {streaming
              ? bpm == null
                ? "waiting for first beat…"
                : z
                  ? `Zone ${zone} · ${z.name}`
                  : "add date of birth for zones"
              : idleText}
          </div>
        </div>
        {rmssd != null && (
          <div className="ml-auto text-right">
            <div className="text-sm font-semibold tabular-nums text-violet-300">{Math.round(rmssd)}</div>
            <div className="text-[9px] uppercase tracking-wide text-neutral-500">HRV ms</div>
          </div>
        )}
      </div>

      {/* Zone bar — five segments, the current one lit (Garmin-style). */}
      {maxHr != null && (
        <div className="mt-2 flex gap-0.5" title={`Max HR ≈ ${maxHr} bpm (from age)`}>
          {ZONES.slice(1).map((zz, i) => (
            <div
              key={zz.name}
              className="h-1 flex-1 rounded-full"
              style={{ background: zz.color, opacity: zone === i + 1 && beating ? 1 : 0.18 }}
            />
          ))}
        </div>
      )}

      {trace.length > 1 && <HrLine trace={trace} dim={!streaming} />}
    </div>
  );
}

function HrLine({ trace, dim }: { trace: number[]; dim: boolean }) {
  const W = 260;
  const H = 40;
  const lo = Math.min(...trace) - 5;
  const hi = Math.max(...trace) + 5;
  const x = (i: number) => (i / (trace.length - 1)) * W;
  const y = (b: number) => H - ((b - lo) / (hi - lo)) * H;
  const line = trace.map((b, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(b).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 h-10 w-full" preserveAspectRatio="none" aria-hidden>
      <defs>
        <linearGradient id="hr-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="#ef4444" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${line} L${W},${H} L0,${H} Z`} fill="url(#hr-fill)" opacity={dim ? 0.4 : 1} />
      <path
        d={line}
        fill="none"
        stroke="#ef4444"
        strokeWidth="1.5"
        strokeOpacity={dim ? 0.4 : 1}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function WristRow({
  hand,
  unit,
  running,
}: {
  hand: ImuHand;
  unit: ImuUnitStatus | undefined;
  running: boolean;
}) {
  const trace = unit?.trace ?? [];
  const now = trace.length ? trace[trace.length - 1] : null;
  const color = WRIST_COLOR[hand];
  const W = 160;
  const H = 28;
  // √ scale over the sensor's ±16 g range: 1 g at rest stays visible, punches don't clip.
  const y = (g: number) => H - Math.sqrt(Math.min(g, 16) / 16) * H;
  const x = (i: number) => (i / 99) * W; // 100 points = 5 s, right-aligned
  const off = 100 - trace.length;
  const line = trace.map((g, i) => `${i === 0 ? "M" : "L"}${x(i + off).toFixed(1)},${y(g).toFixed(1)}`).join(" ");
  const connected = running && !!unit?.connected;
  const detail = connected
    ? `${hand} wrist · ${unit!.hz.toFixed(0)} Hz${unit!.battery_pct != null ? ` · battery ${unit!.battery_pct}%` : ""}`
    : `${hand} wrist`;
  return (
    <div className="flex items-center gap-2" title={detail}>
      <span
        className="w-3 text-[11px] font-bold"
        style={{ color: connected ? color : "#525252" }}
      >
        {hand === "left" ? "L" : "R"}
      </span>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-7 min-w-0 flex-1" preserveAspectRatio="none" aria-hidden>
        <line x1={0} x2={W} y1={y(1)} y2={y(1)} stroke="#262626" strokeDasharray="2 3" />
        {trace.length > 1 && (
          <>
            <path d={`${line} L${W},${H} L${x(off)},${H} Z`} fill={color} opacity={0.15} />
            <path d={line} fill="none" stroke={color} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
          </>
        )}
      </svg>
      <div className="w-14 text-right leading-tight">
        <div className="text-xs font-semibold tabular-nums" style={{ color: connected ? "#fafafa" : "#525252" }}>
          {connected && now != null ? `${now.toFixed(1)}g` : "--"}
        </div>
        <div className="text-[9px] tabular-nums text-neutral-500">
          {connected ? `peak ${unit!.peak_g.toFixed(1)}g` : running ? "connecting" : ""}
        </div>
      </div>
    </div>
  );
}

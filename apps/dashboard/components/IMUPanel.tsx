"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type IMUSample, type PunchEvent } from "@/lib/api";

interface Props {
  sessionId: string;
  /** Punch events on the same T₀ axis — drawn as ticks under the trace
   *  so CV vs IMU alignment is visible at a glance. */
  punchEvents?: PunchEvent[];
}

// Same colours as the CV punch ticks: left = sky, right = green.
const HAND_COLOR: Record<string, string> = {
  left: "rgb(56, 189, 248)",
  right: "rgb(34, 197, 94)",
  none: "rgb(251, 191, 36)", // synthetic / unlabelled stream
};

/**
 * IMU panel — accelerometer magnitude per wrist over the session timeline. Shares
 * the t_ms axis with CV punches so an aligned event = co-located tick. Refreshes
 * every few seconds while the wrist sensors are recording.
 */
export function IMUPanel({ sessionId, punchEvents = [] }: Props) {
  const [samples, setSamples] = useState<IMUSample[] | null>(null);
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const wasLive = useRef(false);

  const refresh = useCallback(async () => {
    try {
      setSamples(await api.imuSamples(sessionId));
    } catch (e) {
      setErr(String(e));
    }
  }, [sessionId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // While the sensors stream, re-pull the (server-thinned) trace every 3 s; one
  // last pull when they stop picks up the final flush.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      const st = await api.imuBleStatus(sessionId).catch(() => null);
      if (!alive) return;
      const running = !!st?.running;
      setLive(running);
      if (running || wasLive.current) refresh();
      wasLive.current = running;
    };
    tick();
    const id = setInterval(tick, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [sessionId, refresh]);

  const synth = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.synthesizeIMU(sessionId);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const empty = !samples || samples.length === 0;

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">IMU (wrist accelerometers)</h2>
        <span className="flex items-center gap-2 text-xs text-neutral-500">
          {live && (
            <span className="flex items-center gap-1 text-red-300">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-500" />
              live
            </span>
          )}
          {empty ? "no samples" : `${samples!.length} points`}
        </span>
      </div>
      {empty ? (
        <div className="mt-2 space-y-2">
          <p className="text-xs text-neutral-500">
            No wrist data for this session. The sensors record when the cameras start, if this
            session&apos;s fighter wears them (see the fighter&apos;s IMU tab). To dry-run the
            fused pipeline without hardware, synthesize a stream from the CV punches.
          </p>
          <button
            disabled={busy}
            onClick={synth}
            className="rounded-xl border border-amber-600/60 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-600/10 disabled:opacity-40"
          >
            {busy ? "Synthesizing…" : "Synthesize from CV punches"}
          </button>
        </div>
      ) : (
        <IMUTrace samples={samples!} punchEvents={punchEvents} />
      )}
      {err && <p className="mt-2 text-xs text-red-300">{err}</p>}
    </section>
  );
}

function IMUTrace({
  samples,
  punchEvents,
}: {
  samples: IMUSample[];
  punchEvents: PunchEvent[];
}) {
  const W = 720;
  const H = 140;
  const PAD = 24;
  const tMin = samples[0].t_ms;
  const tMax = samples[samples.length - 1].t_ms;
  const tSpan = Math.max(1, tMax - tMin);
  const mag = (s: IMUSample) => Math.hypot(s.ax_g, s.ay_g, s.az_g);
  const maxG = Math.max(2.5, ...samples.map(mag));
  const x = (t: number) => PAD + ((t - tMin) / tSpan) * (W - PAD * 2);
  const y = (g: number) => H - PAD - (g / maxG) * (H - PAD * 2);

  // One trace per wrist (samples arrive interleaved and time-sorted).
  const byHand = new Map<string, IMUSample[]>();
  for (const s of samples) {
    const k = s.hand ?? "none";
    if (!byHand.has(k)) byHand.set(k, []);
    byHand.get(k)!.push(s);
  }
  const traces = Array.from(byHand.entries()).map(([hand, rows]) => {
    const peak = Math.max(...rows.map(mag));
    const path = rows
      .map((s, i) => `${i === 0 ? "M" : "L"}${x(s.t_ms).toFixed(1)},${y(mag(s)).toFixed(1)}`)
      .join(" ");
    return { hand, peak, path, impacts: rows.filter((s) => mag(s) > 3.0).length };
  });

  return (
    <div className="mt-2">
      <div className="flex flex-wrap gap-4 text-xs text-neutral-400">
        {traces.map((t) => (
          <span key={t.hand} className="flex items-center gap-1">
            <span
              className="inline-block h-0.5 w-3"
              style={{ background: HAND_COLOR[t.hand] ?? HAND_COLOR.none }}
            />
            {t.hand === "none" ? "synthetic" : t.hand} peak{" "}
            <strong className="text-neutral-200">{t.peak.toFixed(2)} g</strong>
            <span className="text-neutral-500">· &gt;3g {t.impacts}</span>
          </span>
        ))}
        <span>cv punches <strong className="text-emerald-300">{punchEvents.length}</strong></span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full">
        {/* gridlines */}
        <line x1={PAD} x2={W - PAD} y1={y(1)} y2={y(1)} stroke="#262626" strokeDasharray="2 3" />
        <line x1={PAD} x2={W - PAD} y1={y(3)} y2={y(3)} stroke="#404040" strokeDasharray="2 3" />
        <text x={PAD + 2} y={y(3) - 2} fill="#a3a3a3" fontSize="9">3g threshold</text>
        {/* IMU traces */}
        {traces.map((t) => (
          <path
            key={t.hand}
            d={t.path}
            fill="none"
            stroke={HAND_COLOR[t.hand] ?? HAND_COLOR.none}
            strokeOpacity={0.85}
            strokeWidth="1"
          />
        ))}
        {/* CV punch ticks at the bottom */}
        {punchEvents.map((p, i) => (
          <line
            key={i}
            x1={x(p.t_ms)}
            x2={x(p.t_ms)}
            y1={H - PAD + 2}
            y2={H - PAD + 10}
            stroke={p.hand === "right" ? HAND_COLOR.right : HAND_COLOR.left}
            strokeWidth="1"
          />
        ))}
        {/* axis label */}
        <text x={W / 2} y={H - 4} fill="#737373" fontSize="9" textAnchor="middle">
          time (ms since session start)
        </text>
      </svg>
    </div>
  );
}

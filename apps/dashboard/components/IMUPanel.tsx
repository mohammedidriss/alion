"use client";

import { useEffect, useState } from "react";
import { api, type IMUSample, type PunchEvent } from "@/lib/api";

interface Props {
  sessionId: string;
  /** Punch events on the same T₀ axis — drawn as ticks under the trace
   *  so CV vs IMU alignment is visible at a glance. */
  punchEvents?: PunchEvent[];
}

/**
 * IMU panel — accelerometer magnitude over the session timeline. Shares
 * the t_ms axis with CV punches so an aligned event = co-located tick.
 */
export function IMUPanel({ sessionId, punchEvents = [] }: Props) {
  const [samples, setSamples] = useState<IMUSample[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setSamples(await api.imuSamples(sessionId));
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

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
        <h2 className="font-medium">IMU (wrist accelerometer)</h2>
        <span className="text-xs text-neutral-500">
          {empty ? "no samples" : `${samples!.length} samples`}
        </span>
      </div>
      {empty ? (
        <div className="mt-2 space-y-2">
          <p className="text-xs text-neutral-500">
            No IMU stream for this session yet. Until a wrist sensor is
            wired up, generate a synthetic stream from the CV punch
            events to dry-run the fused pipeline.
          </p>
          <button
            disabled={busy}
            onClick={synth}
            className="rounded-xl bg-amber-600 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-500 disabled:bg-neutral-700"
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
  const mags = samples.map((s) => Math.hypot(s.ax_g, s.ay_g, s.az_g));
  const maxG = Math.max(2.5, ...mags);
  const x = (t: number) => PAD + ((t - tMin) / tSpan) * (W - PAD * 2);
  const y = (g: number) => H - PAD - (g / maxG) * (H - PAD * 2);
  const path = mags
    .map((g, i) => `${i === 0 ? "M" : "L"}${x(samples[i].t_ms).toFixed(1)},${y(g).toFixed(1)}`)
    .join(" ");

  const peakG = Math.max(...mags);
  const nImpacts = mags.filter((m) => m > 3.0).length;

  return (
    <div className="mt-2">
      <div className="flex gap-4 text-xs text-neutral-400">
        <span>peak <strong className="text-amber-300">{peakG.toFixed(2)} g</strong></span>
        <span>impacts (&gt;3g) <strong className="text-amber-300">{nImpacts}</strong></span>
        <span>cv punches <strong className="text-emerald-300">{punchEvents.length}</strong></span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2 w-full">
        {/* gridlines */}
        <line x1={PAD} x2={W - PAD} y1={y(1)} y2={y(1)} stroke="#262626" strokeDasharray="2 3" />
        <line x1={PAD} x2={W - PAD} y1={y(3)} y2={y(3)} stroke="#404040" strokeDasharray="2 3" />
        <text x={PAD + 2} y={y(3) - 2} fill="#a3a3a3" fontSize="9">3g threshold</text>
        {/* IMU trace */}
        <path d={path} fill="none" stroke="rgb(251, 191, 36)" strokeWidth="1" />
        {/* CV punch ticks at the bottom */}
        {punchEvents.map((p, i) => (
          <line
            key={i}
            x1={x(p.t_ms)}
            x2={x(p.t_ms)}
            y1={H - PAD + 2}
            y2={H - PAD + 10}
            stroke={p.hand === "right" ? "rgb(34, 197, 94)" : "rgb(56, 189, 248)"}
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

"use client";

import { useMemo } from "react";
import { HrvMetric, ReadinessGauge } from "@/components/HrvCharts";
import type { PunchEvent, Session } from "@/lib/api";

interface SessionWithEvents {
  session: Session;
  events: PunchEvent[];
}

interface Props {
  sessionsWithEvents: SessionWithEvents[];
}

interface PerSessionMetrics {
  session: Session;
  punches: number;
  peakVelocityP90: number;
  peakVelocity: number;
  ppm: number;
  durationMin: number;
  score: number;
}

function p90(values: number[]): number {
  if (!values.length) return 0;
  if (values.length === 1) return values[0];
  const s = [...values].sort((a, b) => a - b);
  const k = (s.length - 1) * 0.9;
  const lo = Math.floor(k);
  const hi = Math.min(lo + 1, s.length - 1);
  return s[lo] * (1 - (k - lo)) + s[hi] * (k - lo);
}

function metricsFor(s: SessionWithEvents): PerSessionMetrics {
  const vels = s.events.map((e) => e.velocity_ms);
  const durationMin = s.session.duration_ms / 60_000;
  const ppm = durationMin > 0 ? s.events.length / durationMin : 0;
  const peakP90 = p90(vels);
  const peak = vels.length ? Math.max(...vels) : 0;
  const score = peakP90 * (ppm / 60) * durationMin;
  return {
    session: s.session,
    punches: s.events.length,
    peakVelocityP90: peakP90,
    peakVelocity: peak,
    ppm,
    durationMin,
    score,
  };
}

export function FighterDashboard({ sessionsWithEvents }: Props) {
  const usable = useMemo(
    () =>
      sessionsWithEvents
        .filter((s) => s.session.status === "completed" && s.events.length > 0)
        .map(metricsFor)
        .sort(
          (a, b) =>
            new Date(a.session.started_at).getTime() -
            new Date(b.session.started_at).getTime(),
        ),
    [sessionsWithEvents],
  );

  const totals = useMemo(() => {
    const totalPunches = usable.reduce((s, m) => s + m.punches, 0);
    const totalDurationMin = usable.reduce((s, m) => s + m.durationMin, 0);
    const avgScore = usable.length
      ? usable.reduce((s, m) => s + m.score, 0) / usable.length
      : 0;
    return { totalPunches, totalDurationMin, avgScore };
  }, [usable]);

  const latestUsable = usable[usable.length - 1];
  const previous = usable[usable.length - 2];
  const delta = latestUsable && previous ? latestUsable.score - previous.score : 0;

  return (
    <section className="space-y-5">
      {/* HERO: most actionable signals — current score callout + progress + readiness */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h3 className="text-base font-semibold">Performance progress</h3>
            <span className="text-xs text-neutral-500">
              score per session, chronological
            </span>
          </div>
          {usable.length === 0 ? (
            <div className="mt-4 flex h-40 items-center justify-center rounded-xl border border-dashed border-white/5 text-xs text-neutral-500">
              no completed sessions with detected punches yet
            </div>
          ) : (
            <>
              <div className="mt-3 flex flex-wrap items-end gap-x-6 gap-y-2">
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-neutral-500">
                    Latest score
                  </div>
                  <div className="text-3xl font-bold tabular-nums">
                    {latestUsable.score.toFixed(2)}
                  </div>
                </div>
                {previous && (
                  <div>
                    <div className="text-[10px] uppercase tracking-wide text-neutral-500">
                      vs previous
                    </div>
                    <div
                      className={`text-lg font-semibold tabular-nums ${
                        delta >= 0 ? "text-lime-300" : "text-red-300"
                      }`}
                    >
                      {delta >= 0 ? "+" : ""}
                      {delta.toFixed(2)}
                    </div>
                  </div>
                )}
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-neutral-500">
                    Avg of {usable.length}
                  </div>
                  <div className="text-lg font-semibold tabular-nums text-neutral-300">
                    {totals.avgScore.toFixed(2)}
                  </div>
                </div>
              </div>
              <ProgressChart series={usable} />
            </>
          )}
        </div>
        <ReadinessSidecar
          sessions={sessionsWithEvents.map((s) => s.session)}
        />
      </div>

      {/* SECONDARY: cumulative volume — important context, but less actionable per session */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          tint="purple"
          icon="●"
          label="Total Punches"
          value={totals.totalPunches.toLocaleString()}
          hint={`${usable.length} session${usable.length === 1 ? "" : "s"}`}
        />
        <StatCard
          tint="orange"
          icon="▶"
          label="Sessions"
          value={sessionsWithEvents.length}
          hint={`${usable.length} usable`}
        />
        <StatCard
          tint="red"
          icon="⏱"
          label="Active Minutes"
          value={
            totals.totalDurationMin >= 1
              ? totals.totalDurationMin.toFixed(0)
              : totals.totalDurationMin.toFixed(1)
          }
          hint={`${(totals.totalDurationMin / 60).toFixed(2)} h capture`}
        />
        <StatCard
          tint="lime"
          icon="◆"
          label="Avg Score"
          value={usable.length ? totals.avgScore.toFixed(2) : "—"}
          hint="peak_v_p90 × ppm/60 × min"
        />
      </div>
    </section>
  );
}

function StatCard({
  tint,
  icon,
  label,
  value,
  hint,
}: {
  tint: "purple" | "orange" | "red" | "lime";
  icon: string;
  label: string;
  value: string | number;
  hint?: string;
}) {
  const iconBg = {
    purple: "bg-violet-500/20 text-violet-300",
    orange: "bg-orange-500/20 text-orange-300",
    red: "bg-red-500/20 text-red-300",
    lime: "bg-lime-500/20 text-lime-300",
  }[tint];
  return (
    <div className={`card card-tinted-${tint} flex items-start gap-3`}>
      <div className={`stat-icon ${iconBg}`} aria-hidden>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs uppercase tracking-wide text-neutral-400">{label}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
        {hint && (
          <div className="mt-1 truncate text-xs text-neutral-500" title={hint}>
            {hint}
          </div>
        )}
      </div>
    </div>
  );
}

function ProgressChart({ series }: { series: PerSessionMetrics[] }) {
  const W = 800;
  const H = 220;
  const padL = 48;
  const padR = 24;
  const padT = 16;
  const padB = 36;
  const xs = series.map((_, i) => i);
  const ys = series.map((m) => m.score);
  const yMax = Math.max(...ys, 0.001) * 1.15;
  const xMax = Math.max(xs.length - 1, 1);
  const sx = (i: number) => padL + (i / xMax) * (W - padL - padR);
  const sy = (y: number) => H - padB - (y / yMax) * (H - padT - padB);
  const path = series
    .map((m, i) => `${i === 0 ? "M" : "L"} ${sx(i)} ${sy(m.score)}`)
    .join(" ");
  const yTicks = 4;
  const yTickVals = Array.from(
    { length: yTicks + 1 },
    (_, i) => (yMax * i) / yTicks,
  );
  return (
    <div className="mt-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        style={{ maxHeight: 240 }}
        role="img"
      >
        {yTickVals.map((v, i) => (
          <g key={i}>
            <line
              x1={padL}
              x2={W - padR}
              y1={sy(v)}
              y2={sy(v)}
              stroke="#1f2937"
              strokeWidth={1}
            />
            <text
              x={padL - 8}
              y={sy(v)}
              fill="#737373"
              fontSize={10}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {v.toFixed(2)}
            </text>
          </g>
        ))}
        <path
          d={path}
          fill="none"
          stroke="#fbbf24"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {series.map((m, i) => {
          const prev = i > 0 ? series[i - 1].score : m.score;
          const delta = m.score - prev;
          return (
            <circle
              key={m.session.id}
              cx={sx(i)}
              cy={sy(m.score)}
              r={4}
              fill={delta >= 0 ? "#a3e635" : "#f87171"}
              stroke="#0a0a0f"
              strokeWidth={1.5}
            >
              <title>
                {`${new Date(m.session.started_at).toLocaleString()}\nscore ${m.score.toFixed(2)} (${delta >= 0 ? "+" : ""}${delta.toFixed(2)} vs prev)\n${m.punches} punches · peak ${m.peakVelocity.toFixed(1)} m/s · ${m.ppm.toFixed(0)} ppm`}
              </title>
            </circle>
          );
        })}
        <text
          x={padL}
          y={H - 8}
          fill="#737373"
          fontSize={10}
        >
          {series.length > 0
            ? new Date(series[0].session.started_at).toLocaleDateString()
            : ""}
        </text>
        <text
          x={W - padR}
          y={H - 8}
          fill="#737373"
          fontSize={10}
          textAnchor="end"
        >
          {series.length > 0
            ? new Date(
                series[series.length - 1].session.started_at,
              ).toLocaleDateString()
            : ""}
        </text>
      </svg>
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500">
        <span>● recent up vs prev: green dot</span>
        <span>● recent down vs prev: red dot</span>
        <span className="ml-auto">{series.length} sessions plotted</span>
      </div>
    </div>
  );
}


function ReadinessSidecar({ sessions }: { sessions: Session[] }) {
  const baselined = sessions
    .filter((s) => s.baseline_rmssd_ms != null)
    .sort((a, b) =>
      (b.baseline_recorded_at ?? "").localeCompare(a.baseline_recorded_at ?? ""),
    );
  const latest = baselined[0];

  if (!latest) {
    return (
      <div className="card flex flex-col">
        <div className="flex items-baseline justify-between">
          <h3 className="text-base font-semibold">Readiness</h3>
          <span className="text-[10px] uppercase tracking-wider text-neutral-500">
            HRV
          </span>
        </div>
        <div className="mt-4 flex flex-1 flex-col items-center justify-center text-center text-xs text-neutral-500">
          <p>No HRV baseline yet.</p>
          <p className="mt-1">
            Upload a 5-min RR CSV on a pending session to populate this.
          </p>
        </div>
      </div>
    );
  }

  const rmssd = latest.baseline_rmssd_ms!;
  const readiness = Math.round(
    Math.max(0, Math.min(1, (rmssd - 20) / 70)) * 100,
  );

  return (
    <div className="card flex flex-col">
      <div className="flex items-baseline justify-between">
        <h3 className="text-base font-semibold">Readiness</h3>
        <span className="text-[10px] uppercase tracking-wider text-neutral-500">
          RMSSD-based
        </span>
      </div>
      <div className="mt-2 flex justify-center">
        <ReadinessGauge value={readiness} />
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
        <HrvMetric label="RMSSD" value={rmssd.toFixed(1)} unit="ms" />
        <HrvMetric
          label="SDNN"
          value={latest.baseline_sdnn_ms?.toFixed(1)}
          unit="ms"
        />
        <HrvMetric
          label="Mean HR"
          value={latest.baseline_mean_hr_bpm?.toFixed(0)}
          unit="bpm"
        />
      </div>
      <p className="mt-auto pt-3 text-[11px] text-neutral-500">
        Latest of {baselined.length} baseline
        {baselined.length === 1 ? "" : "s"}.
      </p>
    </div>
  );
}

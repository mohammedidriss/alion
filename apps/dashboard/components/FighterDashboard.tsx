"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type MatrixResponse, type Session } from "@/lib/api";

interface Props {
  fighterId: string;
  sessions: Session[];
  totalPunches: number;
  peakVelocity: number;
  totalDurationS: number;
}

/**
 * Dashboard hero for the fighter detail page — polished overview at a
 * glance. All metrics derive from real data (CV events + HRV baselines);
 * nothing is fabricated.
 */
export function FighterDashboard({
  fighterId,
  sessions,
  totalPunches,
  peakVelocity,
  totalDurationS,
}: Props) {
  const [matrix, setMatrix] = useState<MatrixResponse | null>(null);

  useEffect(() => {
    api
      .fighterMatrix(fighterId)
      .then(setMatrix)
      .catch(() => setMatrix(null));
  }, [fighterId]);

  const latestBaseline = sessions
    .filter((s) => s.baseline_rmssd_ms != null)
    .sort((a, b) =>
      (b.baseline_recorded_at ?? "").localeCompare(a.baseline_recorded_at ?? ""),
    )[0];

  const rmssd = latestBaseline?.baseline_rmssd_ms ?? null;
  const meanHr = latestBaseline?.baseline_mean_hr_bpm ?? null;
  const sdnn = latestBaseline?.baseline_sdnn_ms ?? null;
  const readiness =
    rmssd != null ? Math.round(Math.max(0, Math.min(1, (rmssd - 20) / 70)) * 100) : null;

  const totalMinutes = totalDurationS / 60;

  return (
    <section className="space-y-4">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard
          tint="purple"
          icon="●"
          label="Total Punches"
          value={totalPunches.toLocaleString()}
          hint={`${sessions.length} session${sessions.length === 1 ? "" : "s"}`}
        />
        <StatCard
          tint="orange"
          icon="↗"
          label="Peak Velocity"
          value={peakVelocity > 0 ? peakVelocity.toFixed(1) : "—"}
          unit="m/s"
          hint={
            peakVelocity > 0 ? "fastest measured" : "no events yet"
          }
        />
        <StatCard
          tint="red"
          icon="⏱"
          label="Active Minutes"
          value={totalMinutes >= 1 ? totalMinutes.toFixed(0) : totalMinutes.toFixed(1)}
          hint={`${(totalDurationS / 3600).toFixed(2)} h capture`}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ReadinessCard rmssd={rmssd} sdnn={sdnn} meanHr={meanHr} readiness={readiness} />
        <div className="card lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h3 className="text-base font-semibold">Velocity vs HRV trend</h3>
            <Link
              href={`/fighters/${fighterId}/matrix`}
              className="text-xs text-emerald-400 hover:underline"
            >
              open matrix →
            </Link>
          </div>
          <p className="mt-1 text-xs text-neutral-500">
            Each dot = one session with a recorded resting HRV baseline.
            Higher RMSSD on the X axis means better autonomic recovery.
          </p>
          <div className="mt-3">
            {matrix && matrix.points.length > 0 ? (
              <MiniScatter matrix={matrix} />
            ) : (
              <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-white/5 text-xs text-neutral-500">
                no sessions yet with both an HRV baseline and detected punches
              </div>
            )}
          </div>
          {matrix && matrix.points.length >= 3 && matrix.pearson_r != null && (
            <div className="mt-3 flex flex-wrap gap-3 text-xs text-neutral-400">
              <span>
                Pearson r ={" "}
                <span
                  className={
                    Math.abs(matrix.pearson_r) >= 0.5
                      ? "font-semibold text-emerald-300"
                      : "text-neutral-300"
                  }
                >
                  {matrix.pearson_r.toFixed(2)}
                </span>
              </span>
              <span className="text-neutral-600">·</span>
              <span>{matrix.points.length} sessions in matrix</span>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function StatCard({
  tint,
  icon,
  label,
  value,
  unit,
  hint,
}: {
  tint: "purple" | "orange" | "red";
  icon: string;
  label: string;
  value: string | number;
  unit?: string;
  hint?: string;
}) {
  const iconBg = {
    purple: "bg-violet-500/20 text-violet-300",
    orange: "bg-orange-500/20 text-orange-300",
    red: "bg-red-500/20 text-red-300",
  }[tint];
  return (
    <div className={`card card-tinted-${tint} flex items-start gap-3`}>
      <div className={`stat-icon ${iconBg}`} aria-hidden>
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-xs uppercase tracking-wide text-neutral-400">{label}</div>
        <div className="mt-1 flex items-baseline gap-1">
          <span className="text-3xl font-semibold tabular-nums">{value}</span>
          {unit && <span className="text-sm text-neutral-400">{unit}</span>}
        </div>
        {hint && <div className="mt-1 truncate text-xs text-neutral-500">{hint}</div>}
      </div>
    </div>
  );
}

function ReadinessCard({
  rmssd,
  sdnn,
  meanHr,
  readiness,
}: {
  rmssd: number | null;
  sdnn: number | null;
  meanHr: number | null;
  readiness: number | null;
}) {
  return (
    <div className="card flex flex-col">
      <div className="flex items-baseline justify-between">
        <h3 className="text-base font-semibold">Readiness</h3>
        <span className="text-[10px] uppercase tracking-wider text-neutral-500">
          RMSSD-based
        </span>
      </div>
      {readiness == null ? (
        <div className="mt-4 flex flex-1 flex-col items-center justify-center text-center text-xs text-neutral-500">
          <p>No baseline recorded yet.</p>
          <p className="mt-1">
            Upload a 5-min resting RR CSV on a pending session to populate this
            gauge.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-4 flex justify-center">
            <Gauge value={readiness} />
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2 text-center text-xs">
            <Metric label="RMSSD" value={rmssd?.toFixed(1)} unit="ms" />
            <Metric label="SDNN" value={sdnn?.toFixed(1)} unit="ms" />
            <Metric label="Mean HR" value={meanHr?.toFixed(0)} unit="bpm" />
          </div>
          <p className="mt-3 text-[11px] text-neutral-500">
            Score = clamp((RMSSD − 20)/70). Heuristic; calibrate per fighter
            once history accumulates.
          </p>
        </>
      )}
    </div>
  );
}

function Metric({
  label,
  value,
  unit,
}: {
  label: string;
  value: string | undefined;
  unit: string;
}) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.02] p-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-0.5 font-semibold tabular-nums">{value ?? "—"}</div>
      <div className="text-[10px] text-neutral-600">{unit}</div>
    </div>
  );
}

function Gauge({ value }: { value: number }) {
  const W = 180;
  const H = 110;
  const cx = W / 2;
  const cy = H - 8;
  const r = 76;
  const circ = Math.PI * r;
  const filled = (Math.min(100, Math.max(0, value)) / 100) * circ;
  const arc = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;
  const color =
    value >= 75
      ? "#a3e635"
      : value >= 55
        ? "#facc15"
        : value >= 35
          ? "#fb923c"
          : "#f87171";
  return (
    <svg
      width={W}
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      role="img"
      aria-label={`Readiness ${value}`}
    >
      <path d={arc} fill="none" stroke="#262626" strokeWidth={14} strokeLinecap="round" />
      <path
        d={arc}
        fill="none"
        stroke={color}
        strokeWidth={14}
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circ - filled}`}
      />
      <text
        x={cx}
        y={cy - 14}
        textAnchor="middle"
        fontSize={32}
        fontWeight={700}
        fill="#f5f5f5"
      >
        {value}
      </text>
      <text x={cx} y={cy + 4} textAnchor="middle" fontSize={10} fill="#737373">
        / 100
      </text>
    </svg>
  );
}

function MiniScatter({ matrix }: { matrix: MatrixResponse }) {
  const W = 600;
  const H = 200;
  const padL = 36;
  const padR = 12;
  const padT = 12;
  const padB = 28;
  const pts = matrix.points;
  const xs = pts.map((p) => p.baseline_rmssd_ms);
  const ys = pts.map((p) => p.score);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMax = Math.max(...ys, 0.001) * 1.1;
  const xRange = Math.max(xMax - xMin, 1);
  const sx = (x: number) => padL + ((x - xMin) / xRange) * (W - padL - padR);
  const sy = (y: number) => H - padB - (y / yMax) * (H - padT - padB);

  const sorted = [...pts].sort(
    (a, b) =>
      new Date(a.started_at).getTime() - new Date(b.started_at).getTime(),
  );
  const showLine = matrix.slope != null && matrix.intercept != null && pts.length >= 3;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="HRV vs score">
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <line
          key={t}
          x1={padL}
          x2={W - padR}
          y1={padT + t * (H - padT - padB)}
          y2={padT + t * (H - padT - padB)}
          stroke="#1f2937"
          strokeWidth={1}
        />
      ))}
      <text x={padL} y={H - 6} fontSize={10} fill="#737373">
        {xMin.toFixed(0)} ms
      </text>
      <text x={W - padR} y={H - 6} fontSize={10} fill="#737373" textAnchor="end">
        {xMax.toFixed(0)} ms
      </text>
      {showLine && (
        <line
          x1={sx(xMin)}
          y1={sy((matrix.slope ?? 0) * xMin + (matrix.intercept ?? 0))}
          x2={sx(xMax)}
          y2={sy((matrix.slope ?? 0) * xMax + (matrix.intercept ?? 0))}
          stroke="#10b981"
          strokeWidth={1.5}
          strokeDasharray="4 4"
          opacity={0.7}
        />
      )}
      {sorted.map((p, i) => {
        const recency = sorted.length > 1 ? i / (sorted.length - 1) : 1;
        return (
          <circle
            key={p.session_id}
            cx={sx(p.baseline_rmssd_ms)}
            cy={sy(p.score)}
            r={4 + recency * 3}
            fill={recency > 0.5 ? "#fbbf24" : "#525252"}
            stroke="#0a0a0f"
            strokeWidth={1}
          >
            <title>
              {`${new Date(p.started_at).toLocaleDateString()} · RMSSD ${p.baseline_rmssd_ms.toFixed(1)}ms · score ${p.score.toFixed(2)}`}
            </title>
          </circle>
        );
      })}
    </svg>
  );
}

"use client";

import type { PunchEvent, Session } from "@/lib/api";

/* ---------- Hand split (L vs R) ---------- */

export function HandSplitChart({ events }: { events: PunchEvent[] }) {
  const left = events.filter((e) => e.hand === "left").length;
  const right = events.filter((e) => e.hand === "right").length;
  const total = left + right;
  if (total === 0) {
    return <Empty label="no events yet" />;
  }
  const lp = (left / total) * 100;
  const rp = (right / total) * 100;
  return (
    <div className="space-y-3">
      <div className="flex h-10 overflow-hidden rounded-xl border border-white/5">
        <div
          className="flex items-center justify-end bg-amber-500/70 pr-2 text-xs font-medium text-black"
          style={{ width: `${lp}%` }}
          title={`Left: ${left} (${lp.toFixed(0)}%)`}
        >
          {lp >= 12 ? `L ${left}` : ""}
        </div>
        <div
          className="flex items-center justify-start bg-sky-500/70 pl-2 text-xs font-medium text-black"
          style={{ width: `${rp}%` }}
          title={`Right: ${right} (${rp.toFixed(0)}%)`}
        >
          {rp >= 12 ? `R ${right}` : ""}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-white/5 bg-amber-500/5 p-2">
          <div className="text-[10px] uppercase tracking-wide text-amber-300/80">
            Left
          </div>
          <div className="mt-0.5 font-semibold tabular-nums text-amber-200">
            {left} <span className="text-neutral-500">({lp.toFixed(0)}%)</span>
          </div>
        </div>
        <div className="rounded-lg border border-white/5 bg-sky-500/5 p-2">
          <div className="text-[10px] uppercase tracking-wide text-sky-300/80">
            Right
          </div>
          <div className="mt-0.5 font-semibold tabular-nums text-sky-200">
            {right} <span className="text-neutral-500">({rp.toFixed(0)}%)</span>
          </div>
        </div>
      </div>
      <p className="text-[11px] text-neutral-500">
        Aggregate of {total.toLocaleString()} detected punches across all
        sessions. Asymmetry &gt; 60/40 may flag dominance or compensation.
      </p>
    </div>
  );
}

/* ---------- Velocity distribution histogram ---------- */

export function VelocityDistributionChart({
  events,
}: {
  events: PunchEvent[];
}) {
  if (events.length === 0) {
    return <Empty label="no events yet" />;
  }
  const W = 320;
  const H = 140;
  const padL = 20;
  const padR = 8;
  const padT = 8;
  const padB = 24;

  const vels = events.map((e) => e.velocity_ms);
  const minV = Math.min(...vels);
  const maxV = Math.max(...vels);
  const bucketCount = 8;
  const span = Math.max(maxV - minV, 0.001);
  const bucketSize = span / bucketCount;
  const buckets = Array.from({ length: bucketCount }, (_, i) => ({
    lo: minV + i * bucketSize,
    hi: minV + (i + 1) * bucketSize,
    left: 0,
    right: 0,
  }));
  for (const e of events) {
    const idx = Math.min(
      bucketCount - 1,
      Math.floor((e.velocity_ms - minV) / bucketSize),
    );
    if (e.hand === "left") buckets[idx].left += 1;
    else buckets[idx].right += 1;
  }
  const maxCount = Math.max(...buckets.map((b) => b.left + b.right));
  const barW = (W - padL - padR) / bucketCount;
  const sx = (i: number) => padL + i * barW;
  const sy = (count: number) =>
    H - padB - (count / Math.max(maxCount, 1)) * (H - padT - padB);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
      {buckets.map((b, i) => {
        const x = sx(i) + 1;
        const w = barW - 2;
        const totalH = H - padB - sy(b.left + b.right);
        const lH = (b.left / Math.max(b.left + b.right, 1)) * totalH;
        const rH = totalH - lH;
        return (
          <g key={i}>
            <rect
              x={x}
              y={H - padB - lH}
              width={w}
              height={lH}
              fill="#fbbf24"
              opacity={0.75}
            >
              <title>
                {`${b.lo.toFixed(1)}–${b.hi.toFixed(1)} m/s · L:${b.left}`}
              </title>
            </rect>
            <rect
              x={x}
              y={H - padB - lH - rH}
              width={w}
              height={rH}
              fill="#0ea5e9"
              opacity={0.75}
            >
              <title>
                {`${b.lo.toFixed(1)}–${b.hi.toFixed(1)} m/s · R:${b.right}`}
              </title>
            </rect>
          </g>
        );
      })}
      <text x={padL} y={H - 6} fontSize={10} fill="#737373">
        {minV.toFixed(1)}
      </text>
      <text
        x={W - padR}
        y={H - 6}
        fontSize={10}
        fill="#737373"
        textAnchor="end"
      >
        {maxV.toFixed(1)} m/s
      </text>
    </svg>
  );
}

/* ---------- Session frequency (sessions per week) ---------- */

export function SessionFrequencyChart({ sessions }: { sessions: Session[] }) {
  const completed = sessions
    .filter((s) => s.status === "completed")
    .map((s) => new Date(s.started_at));
  if (completed.length === 0) return <Empty label="no completed sessions" />;

  // Bucket into the last 8 weeks ending now
  const now = new Date();
  const weeks = 8;
  const buckets = Array.from({ length: weeks }, (_, i) => ({
    weekIdx: i,
    label: "",
    count: 0,
  }));
  const msWeek = 7 * 24 * 60 * 60 * 1000;
  for (let i = 0; i < weeks; i++) {
    const weekEnd = new Date(now.getTime() - (weeks - 1 - i) * msWeek);
    buckets[i].label = `${weekEnd.getMonth() + 1}/${weekEnd.getDate()}`;
  }
  for (const d of completed) {
    const weekIdx =
      weeks - 1 - Math.floor((now.getTime() - d.getTime()) / msWeek);
    if (weekIdx >= 0 && weekIdx < weeks) buckets[weekIdx].count += 1;
  }

  const W = 320;
  const H = 140;
  const padL = 20;
  const padR = 8;
  const padT = 8;
  const padB = 24;
  const max = Math.max(...buckets.map((b) => b.count), 1);
  const barW = (W - padL - padR) / weeks;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
      {buckets.map((b, i) => {
        const h = (b.count / max) * (H - padT - padB);
        const x = padL + i * barW + 1;
        return (
          <g key={i}>
            <rect
              x={x}
              y={H - padB - h}
              width={barW - 2}
              height={h}
              fill="#34d399"
              opacity={b.count > 0 ? 0.85 : 0.2}
            >
              <title>{`week of ${b.label}: ${b.count} session${b.count === 1 ? "" : "s"}`}</title>
            </rect>
            {i % 2 === 0 && (
              <text
                x={x + (barW - 2) / 2}
                y={H - 6}
                fontSize={9}
                fill="#737373"
                textAnchor="middle"
              >
                {b.label}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

/* ---------- HRV vs Performance scatter (inline mini) ---------- */

export interface MatrixPointLite {
  baseline_rmssd_ms: number;
  score: number;
  started_at: string;
  session_id: string;
}

export function HrvScoreScatter({
  points,
  pearson_r,
  slope,
  intercept,
}: {
  points: MatrixPointLite[];
  pearson_r: number | null;
  slope: number | null;
  intercept: number | null;
}) {
  if (points.length === 0) return <Empty label="no matched sessions yet" />;
  const W = 600;
  const H = 220;
  const padL = 40;
  const padR = 16;
  const padT = 12;
  const padB = 32;
  const xs = points.map((p) => p.baseline_rmssd_ms);
  const ys = points.map((p) => p.score);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMax = Math.max(...ys, 0.001) * 1.1;
  const xRange = Math.max(xMax - xMin, 1);
  const sx = (x: number) => padL + ((x - xMin) / xRange) * (W - padL - padR);
  const sy = (y: number) => H - padB - (y / yMax) * (H - padT - padB);
  const sorted = [...points].sort(
    (a, b) =>
      new Date(a.started_at).getTime() - new Date(b.started_at).getTime(),
  );
  const showLine = slope != null && intercept != null && points.length >= 3;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
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
      <text x={padL} y={H - 8} fontSize={10} fill="#737373">
        {xMin.toFixed(0)} ms
      </text>
      <text
        x={W - padR}
        y={H - 8}
        fontSize={10}
        fill="#737373"
        textAnchor="end"
      >
        {xMax.toFixed(0)} ms · RMSSD →
      </text>
      <text
        x={6}
        y={padT + 8}
        fontSize={9}
        fill="#737373"
      >
        score
      </text>
      {showLine && (
        <line
          x1={sx(xMin)}
          y1={sy(slope! * xMin + intercept!)}
          x2={sx(xMax)}
          y2={sy(slope! * xMax + intercept!)}
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
      {pearson_r != null && (
        <text
          x={W - padR - 4}
          y={padT + 14}
          fontSize={11}
          fontWeight={600}
          fill={Math.abs(pearson_r) >= 0.5 ? "#34d399" : "#a3a3a3"}
          textAnchor="end"
        >
          r = {pearson_r.toFixed(2)}
        </text>
      )}
    </svg>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div className="flex h-32 items-center justify-center rounded-xl border border-dashed border-white/5 text-xs text-neutral-500">
      {label}
    </div>
  );
}

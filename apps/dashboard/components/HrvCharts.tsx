"use client";

import type { Session } from "@/lib/api";

export function ReadinessGauge({ value }: { value: number }) {
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
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img">
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

export function HrvMetric({
  label,
  value,
  unit,
}: {
  label: string;
  value: string | undefined;
  unit: string;
}) {
  return (
    <div className="rounded-lg border border-white/5 bg-black/20 p-2">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">{label}</div>
      <div className="mt-0.5 font-semibold tabular-nums">{value ?? "—"}</div>
      <div className="text-[10px] text-neutral-600">{unit}</div>
    </div>
  );
}

export function RmssdTrend({ sessions }: { sessions: Session[] }) {
  const W = 600;
  const H = 160;
  const padL = 40;
  const padR = 16;
  const padT = 12;
  const padB = 28;
  const ys = sessions.map((s) => s.baseline_rmssd_ms!);
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys) * 1.1 || 1;
  const xMax = Math.max(sessions.length - 1, 1);
  const sx = (i: number) => padL + (i / xMax) * (W - padL - padR);
  const sy = (y: number) =>
    H - padB - ((y - yMin) / (yMax - yMin)) * (H - padT - padB);
  const path = sessions
    .map((s, i) => `${i === 0 ? "M" : "L"} ${sx(i)} ${sy(s.baseline_rmssd_ms!)}`)
    .join(" ");
  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="mt-2 w-full"
      style={{ maxHeight: 220 }}
      role="img"
    >
      {[0, 0.5, 1].map((t) => (
        <line
          key={t}
          x1={padL}
          x2={W - padR}
          y1={padT + t * (H - padT - padB)}
          y2={padT + t * (H - padT - padB)}
          stroke="#1f2937"
        />
      ))}
      <text
        x={padL - 6}
        y={sy(yMax)}
        fill="#737373"
        fontSize={10}
        textAnchor="end"
        dominantBaseline="middle"
      >
        {yMax.toFixed(0)}
      </text>
      <text
        x={padL - 6}
        y={sy(yMin)}
        fill="#737373"
        fontSize={10}
        textAnchor="end"
        dominantBaseline="middle"
      >
        {yMin.toFixed(0)}
      </text>
      <path d={path} fill="none" stroke="#34d399" strokeWidth={2} strokeLinejoin="round" />
      {sessions.map((s, i) => (
        <circle
          key={s.id}
          cx={sx(i)}
          cy={sy(s.baseline_rmssd_ms!)}
          r={3}
          fill="#34d399"
          stroke="#0a0a0f"
        >
          <title>
            {`${new Date(s.started_at).toLocaleDateString()} · RMSSD ${s.baseline_rmssd_ms!.toFixed(1)} ms`}
          </title>
        </circle>
      ))}
    </svg>
  );
}

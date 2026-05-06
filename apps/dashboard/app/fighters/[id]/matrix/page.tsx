"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Fighter, type MatrixResponse } from "@/lib/api";

export default function FighterMatrixPage({
  params,
}: {
  params: { id: string };
}) {
  const { id } = params;
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [matrix, setMatrix] = useState<MatrixResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getFighter(id), api.fighterMatrix(id)])
      .then(([f, m]) => {
        setFighter(f);
        setMatrix(m);
      })
      .catch((e) => setErr(String(e)));
  }, [id]);

  if (err)
    return (
      <main className="mx-auto max-w-3xl p-8 text-sm text-red-400">{err}</main>
    );
  if (!fighter || !matrix)
    return (
      <main className="mx-auto max-w-3xl p-8 text-sm text-neutral-400">
        Loading…
      </main>
    );

  const points = matrix.points;
  const usable = points.length >= 3;

  return (
    <main className="mx-auto max-w-4xl space-y-6 p-8">
      <Link
        href={`/fighters/${id}`}
        className="text-sm text-neutral-400 hover:text-neutral-100"
      >
        ← Back to fighter
      </Link>

      <header>
        <h1 className="text-2xl font-semibold">Performance matrix</h1>
        <p className="text-sm text-neutral-400">
          {fighter.name} · resting RMSSD vs CV-derived performance score
        </p>
      </header>

      <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4 text-sm text-neutral-300">
        <p>
          Each dot is one session that has both a recorded resting HRV
          baseline (5-min RR CSV uploaded before the session) AND at least one
          detected punch event. Higher RMSSD = better autonomic recovery
          /readiness. The score is a transparent v1 formula:{" "}
          <code className="rounded bg-neutral-900 px-1 font-mono text-xs">
            peak_v_p90 × ppm/60 × duration_min
          </code>
          .
        </p>
      </section>

      {points.length === 0 ? (
        <p className="text-sm text-neutral-400">
          No sessions yet with both an HRV baseline and detected punches.
          Upload a 5-min resting RR CSV on the session detail page (while the
          session is still pending) to start populating this matrix.
        </p>
      ) : (
        <>
          <Scatter matrix={matrix} />

          <section className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Sessions" value={points.length} />
            <Stat
              label="Pearson r"
              value={
                matrix.pearson_r != null
                  ? matrix.pearson_r.toFixed(2)
                  : "—"
              }
              hint={
                usable && matrix.pearson_r != null
                  ? interpretCorrelation(matrix.pearson_r)
                  : "need 3+ points"
              }
            />
            <Stat
              label="Slope"
              value={
                matrix.slope != null
                  ? matrix.slope.toFixed(3)
                  : "—"
              }
              hint="score per +1 ms RMSSD"
            />
            <Stat
              label="Intercept"
              value={
                matrix.intercept != null
                  ? matrix.intercept.toFixed(2)
                  : "—"
              }
            />
          </section>

          <section className="rounded-lg border border-neutral-800 p-4">
            <h2 className="font-medium">Sessions</h2>
            <table className="mt-3 w-full text-sm">
              <thead className="text-left text-xs uppercase text-neutral-500">
                <tr>
                  <th className="py-1">Date</th>
                  <th>RMSSD (ms)</th>
                  <th>Mean HR</th>
                  <th>Peak v p90</th>
                  <th>PPM</th>
                  <th>Score</th>
                  <th>Punches</th>
                </tr>
              </thead>
              <tbody>
                {[...points]
                  .sort(
                    (a, b) =>
                      new Date(b.started_at).getTime() -
                      new Date(a.started_at).getTime(),
                  )
                  .map((p) => (
                    <tr
                      key={p.session_id}
                      className="border-t border-neutral-800"
                    >
                      <td className="py-1">
                        <Link
                          href={`/sessions/${p.session_id}`}
                          className="text-emerald-400 hover:underline"
                        >
                          {new Date(p.started_at).toLocaleDateString()}
                        </Link>
                      </td>
                      <td className="font-mono">
                        {p.baseline_rmssd_ms.toFixed(1)}
                      </td>
                      <td className="font-mono">
                        {p.baseline_mean_hr_bpm?.toFixed(0) ?? "—"}
                      </td>
                      <td className="font-mono">
                        {p.peak_velocity_p90.toFixed(2)}
                      </td>
                      <td className="font-mono">{p.ppm.toFixed(0)}</td>
                      <td className="font-mono font-medium text-amber-200">
                        {p.score.toFixed(2)}
                      </td>
                      <td className="font-mono">{p.punch_count}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </section>
        </>
      )}
    </main>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 p-3">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="mt-1 text-xs text-neutral-500">{hint}</div>}
    </div>
  );
}

function interpretCorrelation(r: number): string {
  const a = Math.abs(r);
  const dir = r > 0 ? "positive" : "negative";
  if (a < 0.1) return "no correlation";
  if (a < 0.3) return `weak ${dir}`;
  if (a < 0.5) return `moderate ${dir}`;
  if (a < 0.7) return `strong ${dir}`;
  return `very strong ${dir}`;
}

function Scatter({ matrix }: { matrix: MatrixResponse }) {
  const W = 720;
  const H = 360;
  const padL = 56;
  const padR = 16;
  const padT = 16;
  const padB = 40;
  const pts = matrix.points;
  const xs = pts.map((p) => p.baseline_rmssd_ms);
  const ys = pts.map((p) => p.score);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = 0;
  const yMax = Math.max(...ys, 0.001) * 1.1;
  const xRange = Math.max(xMax - xMin, 1);
  const sx = (x: number) =>
    padL + ((x - xMin) / xRange) * (W - padL - padR);
  const sy = (y: number) =>
    H - padB - ((y - yMin) / (yMax - yMin)) * (H - padT - padB);

  const sorted = [...pts].sort(
    (a, b) =>
      new Date(a.started_at).getTime() - new Date(b.started_at).getTime(),
  );
  const n = sorted.length;

  const xTicks = 5;
  const yTicks = 4;
  const xTickVals = Array.from(
    { length: xTicks },
    (_, i) => xMin + ((xMax - xMin) * i) / (xTicks - 1),
  );
  const yTickVals = Array.from(
    { length: yTicks },
    (_, i) => (yMax * i) / (yTicks - 1),
  );

  const showLine =
    matrix.slope != null && matrix.intercept != null && pts.length >= 3;
  const lineX1 = xMin;
  const lineX2 = xMax;
  const lineY1 = (matrix.slope ?? 0) * lineX1 + (matrix.intercept ?? 0);
  const lineY2 = (matrix.slope ?? 0) * lineX2 + (matrix.intercept ?? 0);

  return (
    <figure className="rounded-lg border border-neutral-800 p-4">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label="Resting RMSSD vs performance score scatter"
      >
        {yTickVals.map((v, i) => (
          <g key={`y${i}`}>
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
              fontSize={11}
              textAnchor="end"
              dominantBaseline="middle"
            >
              {v.toFixed(1)}
            </text>
          </g>
        ))}
        {xTickVals.map((v, i) => (
          <text
            key={`x${i}`}
            x={sx(v)}
            y={H - padB + 16}
            fill="#737373"
            fontSize={11}
            textAnchor="middle"
          >
            {v.toFixed(0)}
          </text>
        ))}
        <text
          x={(W - padL - padR) / 2 + padL}
          y={H - 4}
          fill="#a3a3a3"
          fontSize={11}
          textAnchor="middle"
        >
          resting RMSSD (ms) →
        </text>
        <text
          x={14}
          y={padT + (H - padT - padB) / 2}
          fill="#a3a3a3"
          fontSize={11}
          textAnchor="middle"
          transform={`rotate(-90 14 ${padT + (H - padT - padB) / 2})`}
        >
          performance score
        </text>

        {showLine && (
          <line
            x1={sx(lineX1)}
            y1={sy(lineY1)}
            x2={sx(lineX2)}
            y2={sy(lineY2)}
            stroke="#10b981"
            strokeWidth={1.5}
            strokeDasharray="4 4"
            opacity={0.7}
          />
        )}

        {sorted.map((p, i) => {
          const recency = n > 1 ? i / (n - 1) : 1;
          const r = 4 + recency * 4;
          const fill = recency > 0.5 ? "#fbbf24" : "#525252";
          return (
            <circle
              key={p.session_id}
              cx={sx(p.baseline_rmssd_ms)}
              cy={sy(p.score)}
              r={r}
              fill={fill}
              stroke="#0a0a0a"
              strokeWidth={1}
            >
              <title>
                {`${new Date(p.started_at).toLocaleDateString()} · RMSSD ${p.baseline_rmssd_ms.toFixed(1)}ms · score ${p.score.toFixed(2)}`}
              </title>
            </circle>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex items-center justify-between text-xs text-neutral-500">
        <span>older = grey · recent = amber · dot size scales with recency</span>
        <span>
          {pts.length} session{pts.length === 1 ? "" : "s"}
          {showLine && matrix.pearson_r != null && (
            <> · regression r = {matrix.pearson_r.toFixed(2)}</>
          )}
        </span>
      </figcaption>
    </figure>
  );
}

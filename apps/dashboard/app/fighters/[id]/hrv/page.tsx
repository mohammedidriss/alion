"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { HrvMetric, ReadinessGauge, RmssdTrend } from "@/components/HrvCharts";
import { api, type MatrixResponse, type Session } from "@/lib/api";

export default function HrvTab({ params }: { params: { id: string } }) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [matrix, setMatrix] = useState<MatrixResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.listSessions(params.id), api.fighterMatrix(params.id)])
      .then(([s, m]) => {
        setSessions(s);
        setMatrix(m);
      })
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  const baselined = sessions
    .filter((s) => s.baseline_rmssd_ms != null)
    .sort((a, b) => a.started_at.localeCompare(b.started_at));

  if (err)
    return <p className="text-sm text-red-400">{err}</p>;

  if (baselined.length === 0) {
    return (
      <div className="space-y-6">
        <header>
          <h1 className="text-2xl font-semibold">HRV</h1>
          <p className="text-sm text-neutral-400">
            Heart-rate variability — resting baselines and correlation with
            performance.
          </p>
        </header>
        <div className="card text-sm text-neutral-400">
          <p className="font-medium text-neutral-200">
            No HRV baseline recordings yet
          </p>
          <p className="mt-2 text-neutral-500">
            Open a session in <em>pending</em> status and upload a 5-min
            resting RR-interval CSV (single column{" "}
            <code className="rounded bg-black/30 px-1">rr_ms</code> or two
            columns{" "}
            <code className="rounded bg-black/30 px-1">t_ms,rr_ms</code>) to
            populate this tab.
          </p>
          <Link
            href={`/fighters/${params.id}/sessions`}
            className="mt-3 inline-block text-emerald-400 hover:underline"
          >
            View sessions →
          </Link>
        </div>
      </div>
    );
  }

  const latest = baselined[baselined.length - 1];
  const rmssd = latest.baseline_rmssd_ms!;
  const readiness = Math.round(
    Math.max(0, Math.min(1, (rmssd - 20) / 70)) * 100,
  );

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">HRV</h1>
        <p className="text-sm text-neutral-400">
          {baselined.length} session{baselined.length === 1 ? "" : "s"} with
          recorded resting baseline.
        </p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base font-semibold">Latest readiness</h2>
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
          <p className="mt-3 text-[11px] text-neutral-500">
            Score = clamp((RMSSD − 20)/70). Heuristic; calibrate per fighter
            once history accumulates.
          </p>
        </div>

        <div className="card lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base font-semibold">RMSSD trend</h2>
            <Link
              href={`/fighters/${params.id}/matrix`}
              className="text-xs text-emerald-400 hover:underline"
            >
              full matrix →
            </Link>
          </div>
          <RmssdTrend sessions={baselined} />
          {matrix && matrix.points.length >= 3 && matrix.pearson_r != null && (
            <div className="mt-3 text-xs text-neutral-400">
              Score vs RMSSD correlation: Pearson r ={" "}
              <span
                className={
                  Math.abs(matrix.pearson_r) >= 0.5
                    ? "font-semibold text-emerald-300"
                    : "text-neutral-300"
                }
              >
                {matrix.pearson_r.toFixed(2)}
              </span>{" "}
              · {matrix.points.length} matched sessions
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <h2 className="text-base font-semibold">Session baselines</h2>
        <p className="mt-1 text-xs text-neutral-500">
          Every recorded resting baseline, newest first. Click a row to open
          the session.
        </p>
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-xs uppercase text-neutral-500">
            <tr>
              <th className="py-1">Date</th>
              <th>RMSSD (ms)</th>
              <th>SDNN (ms)</th>
              <th>Mean HR</th>
              <th>Source</th>
            </tr>
          </thead>
          <tbody>
            {[...baselined].reverse().map((s) => (
              <tr key={s.id} className="border-t border-white/5">
                <td className="py-2">
                  <Link
                    href={`/sessions/${s.id}`}
                    className="text-emerald-400 hover:underline"
                  >
                    {new Date(s.started_at).toLocaleString()}
                  </Link>
                </td>
                <td className="font-mono">{s.baseline_rmssd_ms!.toFixed(1)}</td>
                <td className="font-mono">
                  {s.baseline_sdnn_ms?.toFixed(1) ?? "—"}
                </td>
                <td className="font-mono">
                  {s.baseline_mean_hr_bpm?.toFixed(0) ?? "—"}
                </td>
                <td className="text-neutral-500">{s.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="card text-xs text-neutral-500">
        <p className="font-medium text-neutral-300">What this tab will track once Polar H10 is online (May 16):</p>
        <ul className="mt-2 list-disc space-y-1 pl-5">
          <li>Live in-session HR + RR streaming during capture</li>
          <li>Inter-round HR recovery curves</li>
          <li>Day-over-day RMSSD drift to flag overtraining</li>
        </ul>
      </div>
    </div>
  );
}

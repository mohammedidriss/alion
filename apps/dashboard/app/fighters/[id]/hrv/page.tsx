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

  const r = matrix?.pearson_r ?? null;
  const correlationStrength =
    r == null
      ? "—"
      : Math.abs(r) < 0.1
        ? "no correlation"
        : Math.abs(r) < 0.3
          ? "weak"
          : Math.abs(r) < 0.5
            ? "moderate"
            : Math.abs(r) < 0.7
              ? "strong"
              : "very strong";

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">HRV</h1>
        <p className="text-sm text-neutral-400">
          {baselined.length} session{baselined.length === 1 ? "" : "s"} with
          recorded resting baseline.
        </p>
      </header>

      {/* HEADLINE STATS — most important numbers, scannable */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <HeadlineStat
          label="Latest readiness"
          value={readiness.toString()}
          unit="/ 100"
          tone={
            readiness >= 75
              ? "lime"
              : readiness >= 55
                ? "yellow"
                : readiness >= 35
                  ? "orange"
                  : "red"
          }
        />
        <HeadlineStat
          label="Latest RMSSD"
          value={rmssd.toFixed(0)}
          unit="ms"
          tone="purple"
        />
        <HeadlineStat
          label="Resting HR"
          value={latest.baseline_mean_hr_bpm?.toFixed(0) ?? "—"}
          unit="bpm"
          tone="orange"
        />
        <HeadlineStat
          label="HRV vs Score r"
          value={r != null ? r.toFixed(2) : "—"}
          unit={correlationStrength}
          tone={r != null && Math.abs(r) >= 0.5 ? "lime" : "neutral"}
        />
      </div>

      {/* PRIMARY CHARTS — readiness gauge + trend, both clearly visible */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="card">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base font-semibold">Readiness gauge</h2>
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
          <p className="mt-2 text-[11px] text-neutral-500">
            Recovery trend across recorded baselines. Drops 7+ ms over a week
            often flag overtraining.
          </p>
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

function HeadlineStat({
  label,
  value,
  unit,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  tone: "lime" | "yellow" | "orange" | "red" | "purple" | "neutral";
}) {
  const valColor = {
    lime: "text-lime-300",
    yellow: "text-yellow-300",
    orange: "text-orange-300",
    red: "text-red-300",
    purple: "text-violet-300",
    neutral: "text-neutral-200",
  }[tone];
  return (
    <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className={`text-2xl font-semibold tabular-nums ${valColor}`}>
          {value}
        </span>
        <span className="text-xs text-neutral-500">{unit}</span>
      </div>
    </div>
  );
}

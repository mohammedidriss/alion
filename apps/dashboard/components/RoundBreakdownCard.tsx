"use client";

import { useEffect, useState } from "react";
import {
  api,
  type RoundExportItem,
  type RoundsExportResponse,
  type SessionStatus,
} from "@/lib/api";

interface Props {
  sessionId: string;
  status: SessionStatus;
}

/**
 * Per-round breakdown — punch count + peak velocity + throughput +
 * a small computed performance score for each round, side-by-side
 * with the HRV / IMU summaries the fused export already provides.
 *
 * Reads `/sessions/{id}/rounds_export` (which is populated for every
 * session — the heuristic detector wrote the events, the round
 * structure was set in /sessions/new). Refetches when the session
 * transitions to `completed` so the card lights up automatically at
 * end of capture.
 */
export function RoundBreakdownCard({ sessionId, status }: Props) {
  const [data, setData] = useState<RoundsExportResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setData(await api.roundsExport(sessionId));
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, status]);

  if (err && !data) {
    return (
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">Per-round breakdown</h2>
        <p className="mt-2 text-xs text-red-300">{err}</p>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">Per-round breakdown</h2>
        <p className="mt-2 text-xs text-neutral-500">Loading…</p>
      </section>
    );
  }

  const totalPunches = data.rounds.reduce((s, r) => s + r.punch_count, 0);
  const peakVelocityOverall = data.rounds.reduce(
    (m, r) => Math.max(m, r.peak_velocity_ms ?? 0),
    0,
  );

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">Per-round breakdown</h2>
        <span className="text-xs text-neutral-500">
          {data.round_count}×{fmtSec(data.round_duration_s)} ·{" "}
          {totalPunches} punches total · peak {peakVelocityOverall.toFixed(2)} m/s
        </span>
      </div>
      <p className="mt-1 text-[11px] text-neutral-500">
        Punches and performance per round. Score is a simple v1 metric
        (peak_v × ppm/60 × duration_min), same shape as the per-fighter
        progress chart so it&apos;s comparable across sessions.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
              <th className="py-1.5 pr-3">Round</th>
              <th className="py-1.5 pr-3">Punches</th>
              <th className="py-1.5 pr-3">Peak v</th>
              <th className="py-1.5 pr-3">ppm</th>
              <th className="py-1.5 pr-3">Score</th>
              <th className="py-1.5 pr-3">Mean HR</th>
              <th className="py-1.5 pr-3">Peak g</th>
              <th className="py-1.5">CV/IMU match</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.rounds.map((r) => (
              <RoundRow key={r.round_number} round={r} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RoundRow({ round: r }: { round: RoundExportItem }) {
  const durationMin = r.duration_ms / 60_000;
  const score =
    r.peak_velocity_ms != null && r.ppm != null
      ? r.peak_velocity_ms * (r.ppm / 60) * durationMin
      : null;
  const fmt = (v: number | null | undefined, d = 2) =>
    v == null ? "—" : v.toFixed(d);
  return (
    <tr className="text-neutral-200">
      <td className="py-2 pr-3 font-medium tabular-nums">
        {r.round_number}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        <span className="text-base font-semibold text-emerald-200">
          {r.punch_count}
        </span>
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.peak_velocity_ms)}{" "}
        <span className="text-[10px] text-neutral-500">m/s</span>
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.ppm, 0)}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        <span className="font-semibold text-amber-200">{fmt(score)}</span>
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.hrv.mean_hr_bpm, 0)}
        {r.hrv.mean_hr_bpm != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">bpm</span>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.imu.peak_g)}
        {r.imu.peak_g != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">g</span>
        )}
      </td>
      <td className="py-2 tabular-nums">
        {r.imu.cv_imu_match_rate == null
          ? "—"
          : `${(r.imu.cv_imu_match_rate * 100).toFixed(0)}%`}
      </td>
    </tr>
  );
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

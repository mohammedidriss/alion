"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  type CrossCheckSummary,
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
 * Reads `/sessions/{id}/rounds_export`. During live capture, polls
 * every 2 s so completed rounds appear progressively as the fighter
 * finishes each one. Stops polling once the session is completed.
 */
export function RoundBreakdownCard({ sessionId, status }: Props) {
  const [data, setData] = useState<RoundsExportResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const prevCompletedRef = useRef(0);

  const refresh = async () => {
    try {
      const d = await api.roundsExport(sessionId);
      setData(d);

      // Track how many rounds have punch data — when a new round
      // completes (punch_count goes from 0 to >0), the UI will
      // naturally re-render and show it.
      const completed = d.rounds.filter((r) => r.punch_count > 0).length;
      prevCompletedRef.current = completed;
    } catch (e) {
      setErr(String(e));
    }
  };

  // The wrist ↔ camera cross-check runs in the background after the cameras'
  // pose lands; poll until it's ready.
  const crossChecking = data?.cross_check?.status === "running";

  useEffect(() => {
    refresh();

    // During live capture, poll every 2 s so each round's results
    // appear as soon as the round ends and punches are assigned.
    const isLive = status === "capturing" || status === "processing";
    if (isLive || crossChecking) {
      const t = setInterval(refresh, isLive ? 2000 : 3000);
      return () => clearInterval(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, status, crossChecking]);

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
  // Multi-camera sessions: the wrist sensors and the cameras cross-checked
  // ("fused"); until that's ready, or without cameras, the wrist sensors alone:
  // counts, left/right and impact in g, but no speed.
  const fused = data.punch_source === "fused";
  const wrist = data.punch_source === "wrist";
  const xc = data.cross_check;
  const totalLeft = data.rounds.reduce(
    (s, r) => s + (fused ? (r.cross_check?.left ?? 0) : r.imu.left),
    0,
  );
  const totalRight = data.rounds.reduce(
    (s, r) => s + (fused ? (r.cross_check?.right ?? 0) : r.imu.right),
    0,
  );
  const peakG = data.rounds.reduce((m, r) => Math.max(m, r.imu.peak_g ?? 0), 0);

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">Per-round breakdown</h2>
        <span className="text-xs text-neutral-500">
          {data.round_count}×{fmtSec(data.round_duration_s)} · {totalPunches} punches total
          {fused || wrist ? ` (L ${totalLeft} · R ${totalRight})` : ""}
          {fused && xc?.agreement != null && ` · ✓ ${pct(xc.agreement)} cross-checked`}
          {wrist && ` · peak ${peakG.toFixed(1)} g`}
          {!fused && !wrist && ` · peak ${peakVelocityOverall.toFixed(2)} m/s`}
        </span>
      </div>
      {fused && xc ? (
        <CrossCheckNote xc={xc} />
      ) : wrist ? (
        <p className="mt-1 text-[11px] text-neutral-500">
          <span className="mr-1 rounded bg-sky-900/60 px-1.5 py-0.5 text-[10px] font-medium text-sky-200">
            From the wrist sensors
          </span>
          Punch counts per round from the wrist IMUs. Score here is impact — the sum of each
          punch&apos;s peak (g).{" "}
          {xc?.status === "running" ? (
            <span className="animate-pulse text-sky-300/90">
              Cross-checking with the cameras…
            </span>
          ) : (
            "Speed needs the cameras' pose, which this session doesn't have."
          )}
        </p>
      ) : data.punch_source === "none" ? (
        <p className="mt-1 text-[11px] text-amber-300/80">
          No punch data: this session has no camera punch events and no wrist-sensor data. Wear
          the wrist sensors to get per-round counts.
        </p>
      ) : (
        <p className="mt-1 text-[11px] text-neutral-500">
          Punches and performance per round. Score is a simple v1 metric
          (peak_v × ppm/60 × duration_min), same shape as the per-fighter
          progress chart so it&apos;s comparable across sessions.
        </p>
      )}
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
              <th className="py-1.5 pr-3">Round</th>
              <th className="py-1.5 pr-3">Punches</th>
              <th className="py-1.5 pr-3">{fused ? "Speed" : "Peak v"}</th>
              <th className="py-1.5 pr-3">ppm</th>
              <th className="py-1.5 pr-3">Score</th>
              <th className="py-1.5 pr-3">Mean HR</th>
              <th className="py-1.5 pr-3">RMSSD</th>
              <th className="py-1.5 pr-3">SDNN</th>
              <th className="py-1.5 pr-3">Peak g</th>
              <th className="py-1.5">
                {fused ? "Cross-check" : wrist ? "Avg impact" : "CV/IMU match"}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.rounds.map((r) => (
              <RoundRow
                key={r.round_number}
                round={r}
                isLive={status === "capturing" || status === "processing"}
                wrist={wrist}
                fused={fused}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RoundRow({
  round: r,
  isLive,
  wrist,
  fused,
}: {
  round: RoundExportItem;
  isLive: boolean;
  wrist: boolean;
  fused: boolean;
}) {
  const durationMin = r.duration_ms / 60_000;
  const x = fused ? r.cross_check : null;
  // Wrist and fused rounds score impact (Σ peak g); camera rounds v × rate.
  const impact = fused || wrist;
  const score = x
    ? x.impact_score
    : wrist
      ? r.imu.impact_score
      : r.peak_velocity_ms != null && r.ppm != null
        ? r.peak_velocity_ms * (r.ppm / 60) * durationMin
        : null;
  const fmt = (v: number | null | undefined, d = 2) =>
    v == null ? "—" : v.toFixed(d);
  const hasData = r.punch_count > 0;
  // During live capture, dim rounds that haven't happened yet.
  const rowClass = isLive && !hasData
    ? "text-neutral-600"
    : "text-neutral-200";
  return (
    <tr className={rowClass}>
      <td className="py-2 pr-3 font-medium tabular-nums">
        {r.round_number}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        <span className="text-base font-semibold text-emerald-200">
          {r.punch_count}
        </span>
        {(wrist || x) && hasData && (
          <span className="ml-1.5 text-[10px] text-neutral-500">
            L {x ? x.left : r.imu.left} · R {x ? x.right : r.imu.right}
          </span>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {x ? (
          <span title="Median speed of the punches both sides confirmed (camera wrist landmark — a relative index, not glove speed)">
            {fmt(x.speed_ms)} <span className="text-[10px] text-neutral-500">m/s</span>
            {x.peak_speed_ms != null && (
              <span className="ml-1 text-[10px] text-neutral-500">
                peak {x.peak_speed_ms.toFixed(1)}
              </span>
            )}
          </span>
        ) : (
          <>
            {fmt(r.peak_velocity_ms)} <span className="text-[10px] text-neutral-500">m/s</span>
          </>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.ppm, 0)}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        <span className="font-semibold text-amber-200">{fmt(score, impact ? 0 : 2)}</span>
        {impact && score != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">Σg</span>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.hrv.mean_hr_bpm, 0)}
        {r.hrv.mean_hr_bpm != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">bpm</span>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.hrv.rmssd_ms, 1)}
        {r.hrv.rmssd_ms != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">ms</span>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.hrv.sdnn_ms, 1)}
        {r.hrv.sdnn_ms != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">ms</span>
        )}
      </td>
      <td className="py-2 pr-3 tabular-nums">
        {fmt(r.imu.peak_g)}
        {r.imu.peak_g != null && (
          <span className="ml-0.5 text-[10px] text-neutral-500">g</span>
        )}
      </td>
      <td className="py-2 tabular-nums">
        {x ? (
          x.agreement == null ? (
            "—"
          ) : (
            <span
              title={`${x.confirmed} seen by both · ${x.wrist_only} wrist only · ${x.camera_only} camera only (sensor dropout) · ${x.unconfirmed} camera hits not counted`}
            >
              <span className={agreementClass(x.agreement)}>✓ {pct(x.agreement)}</span>
              {x.unconfirmed > 0 && (
                <span className="ml-1 text-[10px] text-neutral-500">
                  +{x.unconfirmed} unconf.
                </span>
              )}
            </span>
          )
        ) : wrist ? (
          <>
            {fmt(r.imu.mean_peak_g, 1)}
            {r.imu.mean_peak_g != null && <span className="ml-0.5 text-[10px] text-neutral-500">g</span>}
          </>
        ) : r.imu.cv_imu_match_rate == null ? (
          "—"
        ) : (
          `${(r.imu.cv_imu_match_rate * 100).toFixed(0)}%`
        )}
      </td>
    </tr>
  );
}

/** How the session's punches were settled, and anything either sensor flagged. */
function CrossCheckNote({ xc }: { xc: CrossCheckSummary }) {
  return (
    <div className="mt-1 space-y-1 text-[11px] text-neutral-500">
      <p>
        <span className="mr-1 rounded bg-emerald-900/60 px-1.5 py-0.5 text-[10px] font-medium text-emerald-200">
          {xc.wrist ? "Wrist sensors × cameras" : "Cameras only"}
        </span>
        {xc.wrist ? (
          <>
            A punch counts when the wrist sensors feel it; ✓ means the cameras saw it too and
            gave its speed. Punches only the cameras saw count where a wrist sensor
            wasn&apos;t streaming, otherwise they&apos;re listed as unconfirmed. Score is impact
            (Σ peak g).
          </>
        ) : (
          <>
            No wrist-sensor data, so these are the cameras&apos; estimate: a punch counts when at
            least two cameras saw it. Wear the wrist sensors for counts you can trust.
          </>
        )}
      </p>
      {xc.wrist && (
        <p className="tabular-nums">
          ✓ {xc.confirmed} seen by both · {xc.wrist_only} wrist only
          {xc.camera_only > 0 && ` · ${xc.camera_only} camera only (sensor dropout)`}
          {xc.unconfirmed > 0 && ` · ${xc.unconfirmed} camera hits not counted`}
        </p>
      )}
      {xc.hands_swapped && (
        <p className="rounded border border-amber-700/50 bg-amber-950/40 px-2 py-1 text-amber-200">
          The cameras saw the opposite hand to the wrist sensors on most punches — the sensors
          were on the wrong wrists. Left and right are corrected here. Run the wrist check
          before the next recording.
        </p>
      )}
      {xc.wrist && xc.hands === "unclear" && (
        <p>Left / right as the wrist sensors report them — the cameras couldn&apos;t confirm the hands in this footage.</p>
      )}
      {xc.wrist && xc.cameras.length > 0 && (
        <p className="flex flex-wrap gap-1.5">
          {xc.cameras.map((c) => (
            <span
              key={c.device_id}
              className="rounded bg-white/5 px-1.5 py-0.5"
              title={`${c.punches} punches detected; ${pct(c.agreement)} of them felt by the wrists; saw ${pct(c.coverage)} of the wrist punches`}
            >
              <span className="text-neutral-300">{c.label ?? c.device_id}</span> saw{" "}
              <span className={agreementClass(c.coverage)}>{pct(c.coverage)}</span>
              {c.offset_ms != null && Math.abs(c.offset_ms) >= 100 && (
                <span className="text-amber-300/80">
                  {" "}
                  · clock {c.offset_ms > 0 ? "+" : ""}
                  {Math.round(c.offset_ms)} ms fixed
                </span>
              )}
              {c.hands === "swapped" && !xc.hands_swapped && (
                <span className="text-amber-300/80"> · left/right mirrored?</span>
              )}
            </span>
          ))}
        </p>
      )}
    </div>
  );
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function agreementClass(v: number | null | undefined): string {
  if (v == null) return "text-neutral-400";
  return v >= 0.8 ? "text-emerald-300" : v >= 0.6 ? "text-amber-200" : "text-red-300";
}

function fmtSec(s: number): string {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

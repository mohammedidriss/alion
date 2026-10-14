"use client";

/**
 * Every recorded session of a fighter with what one body sensor stored in it —
 * the heart-rate strap (HRV tab) or the wrist sensors (IMU tab). Sessions where
 * the sensor stored nothing are listed too, so a missed recording is plain to see.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type SessionRecordings, type WristRecording } from "@/lib/api";

type Sensor = "heart" | "wrists";

const TEXT: Record<Sensor, { title: string; what: string; none: string }> = {
  heart: {
    title: "Heart rate in every session",
    what: "From the Polar strap while the cameras recorded. The paired strap connects by itself when a training session opens. Missed, extra and dropped beats are removed before RMSSD and SDNN; with more than 5 % of them, those two aren't reliable (⚠).",
    none: "No heart rate recorded",
  },
  wrists: {
    title: "Wrist sensors in every session",
    what: "From the two wrist sensors while the cameras recorded — about 100 readings a second per wrist.",
    none: "No wrist data recorded",
  },
};

function has(r: SessionRecordings, sensor: Sensor): boolean {
  return sensor === "heart" ? r.heart != null : Object.keys(r.wrists).length > 0;
}

function length(s: number | null | undefined): string {
  if (s == null) return "—";
  const m = Math.floor(s / 60);
  return m ? `${m} min ${Math.round(s % 60)} s` : `${Math.round(s)} s`;
}

const num = (v: number | null | undefined, d = 0) => (v == null ? "—" : v.toFixed(d));

function Wrist({ w }: { w: WristRecording | undefined }) {
  if (!w) return <span className="text-neutral-500">—</span>;
  return (
    <span className="tabular-nums">
      {w.samples.toLocaleString()} · {num(w.hz)} Hz · peak {w.peak_g.toFixed(1)} g
    </span>
  );
}

function HrvCell({ v, reliable, share, last }: { v: number | null; reliable: boolean; share: number; last?: boolean }) {
  return (
    <td
      className={`py-2 tabular-nums ${last ? "" : "pr-3"} ${reliable ? "" : "text-neutral-500"}`}
      title={reliable ? undefined : `${Math.round(share * 100)}% of beats were artifacts — more than 5%, so this isn't reliable`}
    >
      {num(v, 1)} ms{!reliable && v != null && <span className="ml-1 text-amber-300">⚠</span>}
    </td>
  );
}

export function SessionRecordingsCard({ fighterId, sensor }: { fighterId: string; sensor: Sensor }) {
  const [rows, setRows] = useState<SessionRecordings[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [onlyWithData, setOnlyWithData] = useState(false);

  useEffect(() => {
    api
      .fighterRecordings(fighterId)
      .then(setRows)
      .catch((e) => setErr(String(e instanceof Error ? e.message : e)));
  }, [fighterId]);

  const t = TEXT[sensor];
  const withData = rows ? rows.filter((r) => has(r, sensor)).length : 0;
  const shown = rows ? (onlyWithData ? rows.filter((r) => has(r, sensor)) : rows) : [];
  const cols = sensor === "heart" ? 7 : 4;

  return (
    <div className="card">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">{t.title}</h2>
        {rows && (
          <span className="text-sm text-neutral-300">
            <b className="text-emerald-400">{withData}</b> of {rows.length} sessions recorded
          </span>
        )}
      </div>
      <p className="mt-1 text-xs text-neutral-400">{t.what}</p>
      {err && <p className="mt-2 text-sm text-red-400">{err}</p>}
      {rows && rows.length > 0 && (
        <label className="mt-3 flex items-center gap-2 text-xs text-neutral-300">
          <input type="checkbox" checked={onlyWithData} onChange={(e) => setOnlyWithData(e.target.checked)} />
          Only sessions with data
        </label>
      )}
      {rows === null && !err && <p className="mt-3 text-sm text-neutral-500">Loading…</p>}
      {rows && rows.length === 0 && <p className="mt-3 text-sm text-neutral-400">No recorded sessions yet.</p>}
      {shown.length > 0 && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs uppercase text-neutral-400">
              <tr>
                <th className="py-1.5 pr-3">Session</th>
                <th className="py-1.5 pr-3">Length</th>
                {sensor === "heart" ? (
                  <>
                    <th className="py-1.5 pr-3">Beats</th>
                    <th className="py-1.5 pr-3">Avg HR</th>
                    <th className="py-1.5 pr-3">Max HR</th>
                    <th className="py-1.5 pr-3">RMSSD</th>
                    <th className="py-1.5">SDNN</th>
                  </>
                ) : (
                  <>
                    <th className="py-1.5 pr-3">Left wrist</th>
                    <th className="py-1.5">Right wrist</th>
                  </>
                )}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => (
                <tr key={r.session_id} className="border-t border-white/5">
                  <td className="py-2 pr-3">
                    <Link href={`/sessions/${r.session_id}`} className="text-emerald-400 hover:underline">
                      {r.started_at ? new Date(r.started_at).toLocaleString() : "—"}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 tabular-nums text-neutral-300">{length(r.duration_s)}</td>
                  {!has(r, sensor) ? (
                    <td colSpan={cols - 2} className="py-2 text-amber-300/90">
                      {t.none}
                    </td>
                  ) : sensor === "heart" && r.heart ? (
                    <>
                      <td className="py-2 pr-3 tabular-nums">
                        {r.heart.beats}
                        {r.heart.artifacts > 0 && (
                          <span className="ml-1 text-[11px] text-neutral-500">
                            ({r.heart.artifacts} removed)
                          </span>
                        )}
                      </td>
                      <td className="py-2 pr-3 tabular-nums">{num(r.heart.mean_hr_bpm)} bpm</td>
                      <td className="py-2 pr-3 tabular-nums">{num(r.heart.max_hr_bpm)} bpm</td>
                      <HrvCell v={r.heart.rmssd_ms} reliable={r.heart.reliable} share={r.heart.artifact_share} />
                      <HrvCell v={r.heart.sdnn_ms} reliable={r.heart.reliable} share={r.heart.artifact_share} last />
                    </>
                  ) : (
                    <>
                      <td className="py-2 pr-3">
                        <Wrist w={r.wrists.left ?? r.wrists.unknown} />
                      </td>
                      <td className="py-2">
                        <Wrist w={r.wrists.right} />
                      </td>
                    </>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

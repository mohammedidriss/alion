"use client";

import { useEffect, useState } from "react";
import { api, type TakeCrossCheck } from "@/lib/api";

/**
 * How a take's wrist sensors and cameras agree — overall, per camera and per
 * protocol block. Each sensor checks the other: the cameras confirm the wrists'
 * punches and catch sensors strapped to the wrong wrists; the wrists show which
 * camera hits were jitter and whether a camera's clock or angle was off.
 * Reads `/v2/takes/{id}/cross-check`, which is worked out in the background
 * once the cameras' pose lands — polls until it's ready.
 */
export function TakeCrossCheckCard({ takeId }: { takeId: string }) {
  const [xc, setXc] = useState<TakeCrossCheck | null | undefined>(undefined);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        const r = await api.takeCrossCheck(takeId);
        if (!alive) return;
        setXc(r);
        if (r?.status === "running") timer = setTimeout(load, 3000);
      } catch {
        if (alive) setXc(null);
      }
    };
    load();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [takeId]);

  if (xc === undefined || xc === null) return null; // loading, or no camera pose
  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold">Wrist sensors × cameras</h2>
        {xc.status === "ready" && xc.agreement != null && (
          <span className="text-sm text-neutral-400">
            <span className={agreementClass(xc.agreement)}>✓ {pct(xc.agreement)}</span> of{" "}
            {xc.counted} punches seen by both
          </span>
        )}
      </div>

      {xc.status === "running" ? (
        <p className="animate-pulse text-sm text-sky-300/90">
          Cross-checking the wrist sensors against the cameras…
        </p>
      ) : (
        <>
          {xc.hands_swapped &&
            (xc.labels_swapped ? (
              <p className="rounded-lg border border-emerald-800/50 bg-emerald-950/30 px-3 py-2 text-sm text-emerald-200">
                The cameras confirm the wrist sensors were on the wrong wrists — and this
                take&apos;s labels are already corrected (Swap wrists).
              </p>
            ) : (
              <p className="rounded-lg border border-amber-700/50 bg-amber-950/40 px-3 py-2 text-sm text-amber-200">
                The cameras saw the opposite hand to the wrist sensors on most punches — the
                sensors were on the wrong wrists in this take. Use Swap wrists in the protocol
                card below to relabel it before exporting.
              </p>
            ))}
          {!xc.wrist && (
            <p className="text-sm text-amber-300/80">
              No wrist-sensor data in this take — only the cameras&apos; estimate (
              {xc.counted} punches seen by two or more cameras).
            </p>
          )}
          {xc.wrist && (
            <p className="text-xs text-neutral-400 tabular-nums">
              ✓ {xc.confirmed} seen by both · {xc.wrist_only} wrist only
              {xc.camera_only > 0 && ` · ${xc.camera_only} camera only (sensor dropout)`}
              {xc.unconfirmed > 0 && ` · ${xc.unconfirmed} camera hits the wrists didn't feel`}
              {xc.hands === "unclear" && " · left / right not confirmed by the cameras"}
              {xc.hands === "consistent" && " · left / right confirmed"}
            </p>
          )}

          {xc.wrist && xc.cameras.length > 0 && (
            <div className="grid gap-2 sm:grid-cols-3">
              {xc.cameras.map((c) => (
                <div key={c.device_id} className="rounded-xl border border-white/5 bg-black/20 p-3 text-xs">
                  <div className="font-medium text-neutral-200">{c.label ?? c.device_id}</div>
                  <div className="mt-1 text-neutral-400">
                    saw <span className={agreementClass(c.coverage)}>{pct(c.coverage)}</span> of the
                    wrist punches · <span className={agreementClass(c.agreement)}>{pct(c.agreement)}</span>{" "}
                    of its {c.punches} hits confirmed
                  </div>
                  {c.offset_ms != null && Math.abs(c.offset_ms) >= 100 && (
                    <div className="mt-0.5 text-amber-300/80">
                      clock {c.offset_ms > 0 ? "+" : ""}
                      {Math.round(c.offset_ms)} ms — corrected
                    </div>
                  )}
                  {c.hands === "swapped" && !xc.hands_swapped && (
                    <div className="mt-0.5 text-amber-300/80">left / right look mirrored</div>
                  )}
                </div>
              ))}
            </div>
          )}

          {xc.blocks.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
                    <th className="py-1.5 pr-3">Block</th>
                    <th className="py-1.5 pr-3">Punches</th>
                    <th className="py-1.5 pr-3">Seen by both</th>
                    <th className="py-1.5">Camera hits not felt</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {xc.blocks.map((b, i) => (
                    <tr key={`${b.key}-${i}`} className="text-neutral-200">
                      <td className="py-1.5 pr-3">{b.key.replace(/_/g, " ")}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{b.counted}</td>
                      <td className="py-1.5 pr-3 tabular-nums">
                        {b.confirmed}
                        {b.counted > 0 && (
                          <span className={`ml-1.5 ${agreementClass(b.confirmed / b.counted)}`}>
                            {pct(b.confirmed / b.counted)}
                          </span>
                        )}
                      </td>
                      <td className="py-1.5 tabular-nums text-neutral-400">{b.unconfirmed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function pct(v: number | null | undefined): string {
  return v == null ? "—" : `${Math.round(v * 100)}%`;
}

function agreementClass(v: number | null | undefined): string {
  if (v == null) return "text-neutral-400";
  return v >= 0.8 ? "text-emerald-300" : v >= 0.6 ? "text-amber-200" : "text-red-300";
}

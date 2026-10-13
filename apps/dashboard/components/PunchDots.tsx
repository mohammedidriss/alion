"use client";

/**
 * The live punch breakdown (ADR-022). `PunchDots` is the panel under a fighter's
 * cameras: a column per hand, a coloured dot per punch type with its count — jab
 * or cross (by the stance), hook, uppercut — and each hand's total.
 * `PunchOverlay` sits on the video itself, next to the recording badge: the total
 * and the same breakdown, named, from the moment recording starts.
 */

import type { PunchTally } from "@/lib/api";
import { KIND_COLOR, tallyRows } from "@/lib/punchTally";

const HAND = { left: "Left", right: "Right" } as const;

export function PunchDots({
  tally,
  stance,
}: {
  tally: PunchTally | null | undefined;
  stance: string | null | undefined;
}) {
  if (!tally) return null;
  const rows = tallyRows(tally, stance);

  return (
    <div className="grid grid-cols-2 gap-3">
      {rows.map((r) => (
        <div key={r.hand} className="space-y-1.5 rounded-xl bg-white/5 p-2.5">
          <div className="flex items-baseline justify-between text-xs">
            <span className="font-semibold uppercase tracking-wide text-neutral-300">
              {HAND[r.hand]}
              {r.side && <span className="font-normal normal-case text-neutral-500"> · {r.side}</span>}
            </span>
            <span className="text-lg font-bold tabular-nums text-emerald-400">{r.total}</span>
          </div>
          {r.dots.map((d) => (
            <div key={d.kind} className="flex items-center gap-2">
              <span
                className={`grid h-7 min-w-[1.75rem] place-items-center rounded-full px-1.5 text-sm font-bold tabular-nums text-white ${
                  KIND_COLOR[d.kind]
                } ${d.count ? "" : "opacity-30"}`}
              >
                {d.count}
              </span>
              <span className={`text-xs ${d.count ? "text-neutral-200" : "text-neutral-500"}`}>{d.label}</span>
            </div>
          ))}
          {r.unnamed > 0 && (
            <div className="flex items-center gap-2" title="Counted, but the camera couldn't tell which punch">
              <span className="grid h-7 min-w-[1.75rem] place-items-center rounded-full bg-neutral-600 px-1.5 text-sm font-bold tabular-nums text-white">
                {r.unnamed}
              </span>
              <span className="text-xs text-neutral-400">Not sure</span>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function PunchOverlay({
  total,
  tally,
  stance,
  size = "sm",
}: {
  total: number;
  /** null: the camera's page predates the breakdown — reload it. */
  tally: PunchTally | null | undefined;
  stance: string | null | undefined;
  size?: "sm" | "md";
}) {
  const sm = size === "sm";
  const rows = tally ? tallyRows(tally, stance) : null;
  const unnamed = rows ? rows.some((r) => r.unnamed > 0) : false;
  const dot = sm ? "h-3.5 min-w-[0.875rem] px-0.5 text-[9px]" : "h-5 min-w-[1.25rem] px-1 text-[11px]";
  return (
    <div
      className={`pointer-events-none rounded-lg bg-black/75 leading-tight text-white shadow-lg ${
        sm ? "px-1.5 py-1 text-[10px]" : "px-2.5 py-2 text-xs"
      }`}
    >
      <div>
        <b className={`tabular-nums text-emerald-400 ${sm ? "text-sm" : "text-2xl"}`}>{total}</b>{" "}
        punches
      </div>
      {rows ? (
        <div className={`mt-1 grid grid-cols-2 ${sm ? "gap-x-2 gap-y-0.5" : "gap-x-3 gap-y-1"}`}>
          {rows.map((r) => (
            <div key={r.hand} className="font-semibold text-neutral-300">
              {HAND[r.hand]} <span className="tabular-nums text-emerald-400">{r.total}</span>
            </div>
          ))}
          {[0, 1, 2].flatMap((i) =>
            rows.map((r) => {
              const d = r.dots[i];
              return (
                <div key={`${r.hand}-${d.kind}`} className={`flex items-center gap-1 ${d.count ? "" : "opacity-40"}`}>
                  <span
                    className={`grid place-items-center rounded-full font-bold tabular-nums ${dot} ${KIND_COLOR[d.kind]}`}
                  >
                    {d.count}
                  </span>
                  <span className="whitespace-nowrap">{sm ? d.short : d.label}</span>
                </div>
              );
            }),
          )}
          {unnamed &&
            rows.map((r) => (
              <div key={`${r.hand}-unnamed`} className={`flex items-center gap-1 ${r.unnamed ? "" : "opacity-40"}`}>
                <span className={`grid place-items-center rounded-full bg-neutral-600 font-bold tabular-nums ${dot}`}>
                  {r.unnamed}
                </span>
                <span className="whitespace-nowrap">Not sure</span>
              </div>
            ))}
        </div>
      ) : (
        <div className="mt-0.5 text-neutral-400">Reload this camera&apos;s page for the breakdown</div>
      )}
    </div>
  );
}

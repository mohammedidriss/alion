"use client";

/**
 * The live punch breakdown on the camera screens: one row per hand, a coloured
 * dot per punch type with its count — jab or cross (by the stance), hook,
 * uppercut — and each hand's total. `compact` is the small version laid over a
 * camera tile: L/R rows of numbered dots, named in each dot's tooltip.
 */

import type { PunchTally } from "@/lib/api";
import { KIND_COLOR, tallyRows } from "@/lib/punchTally";

const HAND = { left: "Left", right: "Right" } as const;

export function PunchDots({
  tally,
  stance,
  compact = false,
}: {
  tally: PunchTally | null | undefined;
  stance: string | null | undefined;
  compact?: boolean;
}) {
  if (!tally) return null;
  const rows = tallyRows(tally, stance);

  if (compact) {
    return (
      <div className="pointer-events-auto space-y-0.5 rounded-md bg-black/70 px-1.5 py-1 text-[10px] leading-none">
        {rows.map((r) => (
          <div key={r.hand} className="flex items-center gap-1">
            <span
              className="w-6 font-semibold tabular-nums text-neutral-200"
              title={`${HAND[r.hand]} hand${r.side ? ` (${r.side})` : ""}: ${r.total}`}
            >
              {HAND[r.hand][0]}
              <span className="text-emerald-400">{r.total}</span>
            </span>
            {r.dots.map((d) => (
              <span
                key={d.kind}
                title={`${HAND[r.hand]} hand — ${d.label.toLowerCase()}: ${d.count}`}
                className={`grid h-4 min-w-[1rem] place-items-center rounded-full px-1 font-bold tabular-nums text-white ${
                  KIND_COLOR[d.kind]
                } ${d.count ? "" : "opacity-30"}`}
              >
                {d.count}
              </span>
            ))}
          </div>
        ))}
      </div>
    );
  }

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

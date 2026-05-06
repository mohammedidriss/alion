"use client";

import { type PunchEvent, type PunchType } from "@/lib/api";

interface Props {
  events: PunchEvent[];
}

const TYPE_ORDER: PunchType[] = ["jab", "cross", "hook", "uppercut"];
const TYPE_COLORS: Record<PunchType, { bar: string; text: string }> = {
  jab: { bar: "bg-emerald-400", text: "text-emerald-300" },
  cross: { bar: "bg-violet-400", text: "text-violet-300" },
  hook: { bar: "bg-rose-400", text: "text-rose-300" },
  uppercut: { bar: "bg-cyan-400", text: "text-cyan-300" },
};

export function PunchChart({ events }: Props) {
  if (events.length === 0) return null;

  const left = events.filter((e) => e.hand === "left").length;
  const right = events.filter((e) => e.hand === "right").length;
  const maxHand = Math.max(left, right, 1);
  const total = left + right;

  const meanV = events.reduce((s, e) => s + e.velocity_ms, 0) / events.length;
  const maxV = Math.max(...events.map((e) => e.velocity_ms));

  // Per-type counts. `null` (unknown) is shown separately.
  const byType: Record<PunchType, number> = { jab: 0, cross: 0, hook: 0, uppercut: 0 };
  let untyped = 0;
  for (const e of events) {
    if (e.punch_type) byType[e.punch_type] += 1;
    else untyped += 1;
  }
  const maxType = Math.max(...TYPE_ORDER.map((t) => byType[t]), 1);
  const hasTypeData = TYPE_ORDER.some((t) => byType[t] > 0);

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <h2 className="font-medium">By hand</h2>
      <p className="mt-1 text-xs text-neutral-500">
        Total {total} · mean {meanV.toFixed(2)} m/s · peak {maxV.toFixed(2)} m/s
      </p>

      <div className="mt-4 space-y-3">
        <Bar label="Left" count={left} max={maxHand} bar="bg-amber-400" text="text-amber-300" />
        <Bar label="Right" count={right} max={maxHand} bar="bg-sky-400" text="text-sky-300" />
      </div>

      <div className="mt-5 rounded border border-neutral-800 bg-neutral-900/50 p-3">
        <p className="text-xs font-medium text-neutral-300">By punch type</p>
        {hasTypeData ? (
          <>
            <div className="mt-3 space-y-2">
              {TYPE_ORDER.map((t) => {
                const count = byType[t];
                if (count === 0 && untyped === total) return null;
                return (
                  <Bar
                    key={t}
                    label={t.charAt(0).toUpperCase() + t.slice(1)}
                    count={count}
                    max={maxType}
                    bar={TYPE_COLORS[t].bar}
                    text={TYPE_COLORS[t].text}
                  />
                );
              })}
            </div>
            {untyped > 0 && (
              <p className="mt-3 text-xs text-neutral-500">
                {untyped} of {total} unclassified — needs world landmarks (real
                3D pose) to classify type.
              </p>
            )}
            <p className="mt-2 text-xs text-neutral-500">
              Heuristic v0.5 — distinguishes types from wrist trajectory.
              Phase 3 LSTM replaces this with a learned model on the same field.
            </p>
          </>
        ) : (
          <p className="mt-1 text-xs text-neutral-500">
            No type data yet — punch_type is populated for sessions captured
            with world-landmark mode (the new default). Older sessions may
            show this empty.
          </p>
        )}
      </div>
    </section>
  );
}

function Bar({
  label,
  count,
  max,
  bar,
  text,
}: {
  label: string;
  count: number;
  max: number;
  bar: string;
  text: string;
}) {
  const pct = max === 0 ? 0 : (count / max) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className={text}>{label}</span>
        <span className="font-mono">{count}</span>
      </div>
      <div className="mt-1 h-3 overflow-hidden rounded bg-neutral-800">
        <div
          className={`h-full ${bar} transition-[width] duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

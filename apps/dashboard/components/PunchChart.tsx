"use client";

import { type PunchEvent } from "@/lib/api";

interface Props {
  events: PunchEvent[];
}

export function PunchChart({ events }: Props) {
  if (events.length === 0) return null;

  const left = events.filter((e) => e.hand === "left").length;
  const right = events.filter((e) => e.hand === "right").length;
  const max = Math.max(left, right, 1);
  const total = left + right;

  const meanV =
    events.reduce((s, e) => s + e.velocity_ms, 0) / events.length;
  const maxV = Math.max(...events.map((e) => e.velocity_ms));

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <h2 className="font-medium">By hand</h2>
      <p className="mt-1 text-xs text-neutral-500">
        Total {total} · mean {meanV.toFixed(2)} m/s · peak {maxV.toFixed(2)} m/s
      </p>

      <div className="mt-4 space-y-3">
        <Bar
          label="Left"
          count={left}
          max={max}
          color="bg-amber-400"
          textColor="text-amber-300"
        />
        <Bar
          label="Right"
          count={right}
          max={max}
          color="bg-sky-400"
          textColor="text-sky-300"
        />
      </div>

      <div className="mt-5 rounded border border-neutral-800 bg-neutral-900/50 p-3">
        <p className="text-xs font-medium text-neutral-300">
          By punch type (jab · cross · hook · uppercut)
        </p>
        <p className="mt-1 text-xs text-neutral-500">
          Not available yet — punch-type classification requires the LSTM model,
          which lands in Phase 3. Today&apos;s heuristic detector only knows which
          hand fired.
        </p>
      </div>
    </section>
  );
}

function Bar({
  label,
  count,
  max,
  color,
  textColor,
}: {
  label: string;
  count: number;
  max: number;
  color: string;
  textColor: string;
}) {
  const pct = max === 0 ? 0 : (count / max) * 100;
  return (
    <div>
      <div className="flex items-baseline justify-between text-sm">
        <span className={textColor}>{label}</span>
        <span className="font-mono">{count}</span>
      </div>
      <div className="mt-1 h-3 overflow-hidden rounded bg-neutral-800">
        <div
          className={`h-full ${color} transition-[width] duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

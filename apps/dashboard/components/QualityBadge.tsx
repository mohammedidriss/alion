"use client";

/** What a camera sees of the wrists, and how fast its pose runs (ADR-059): a
 *  camera under 70% both-wrists or 25 frames a second miscounts. */

import type { CamQuality } from "@/lib/api";

export const QUALITY_BOTH = 0.7;
export const QUALITY_FPS = 25;

/** What a camera sees of the wrists, and how fast its pose runs (ADR-059). */
export function QualityBadge({ q }: { q: CamQuality }) {
  const ok = q.both >= QUALITY_BOTH && q.fps >= QUALITY_FPS;
  return (
    <span
      title={
        `Both wrists in view ${Math.round(q.both * 100)}% of the last few seconds ` +
        `(left ${Math.round(q.left * 100)}%, right ${Math.round(q.right * 100)}%); ` +
        `pose at ${Math.round(q.fps)} frames a second`
      }
      className={`absolute left-1 top-1 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
        ok ? "bg-black/60 text-emerald-300" : "bg-amber-500/90 text-black"
      }`}
    >
      {ok ? "✓" : "⚠"} both wrists {Math.round(q.both * 100)}% · {Math.round(q.fps)} fps
    </span>
  );
}


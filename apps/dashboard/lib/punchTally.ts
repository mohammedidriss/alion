/**
 * A camera's live punches by hand and type — the dots on the camera screens.
 *
 * Counted by hand (left/right), not lead/rear, so a camera can count before it
 * knows the stance; `tallyRows` names jab/cross and lead/rear once the fighter's
 * stance is known. Types come from `classifyPunchType` (the wrist's direction
 * over the last few frames) — a quick live estimate; the trained model names the
 * punches again after the session (ADR-020). Mirrors `PunchTally` in
 * packages/api/routes/capture_coord.py.
 */

import type { HandTally, PunchTally, PunchType } from "./api";
import type { Hand } from "./punchDetector";

export type PunchKind = "straight" | "hook" | "uppercut";

const emptyHand = (): HandTally => ({ total: 0, straight: 0, hook: 0, uppercut: 0 });

export const emptyTally = (): PunchTally => ({ left: emptyHand(), right: emptyHand() });

/** The tally with one more punch (`type` null: the camera couldn't name it). */
export function addPunch(t: PunchTally, hand: Hand, type: PunchType | null): PunchTally {
  const h = { ...t[hand], total: t[hand].total + 1 };
  if (type) h[type === "jab" || type === "cross" ? "straight" : type] += 1;
  return { ...t, [hand]: h };
}

export const KIND_COLOR: Record<PunchKind, string> = {
  straight: "bg-sky-500",
  hook: "bg-amber-500",
  uppercut: "bg-fuchsia-500",
};

export interface TallyRow {
  hand: Hand;
  side: "lead" | "rear" | null; // null: stance unknown, or a switch hitter
  total: number;
  dots: { kind: PunchKind; label: string; count: number }[];
  unnamed: number; // counted, but the camera couldn't tell the type
}

/** One row per hand, its dots named for the stance: the lead hand's straight is
 *  the jab, the rear hand's the cross. */
export function tallyRows(t: PunchTally, stance: string | null | undefined): TallyRow[] {
  const s = stance?.toLowerCase();
  const lead: Hand | null = s === "orthodox" ? "left" : s === "southpaw" ? "right" : null;
  return (["left", "right"] as const).map((hand) => {
    const h = t[hand];
    const side = lead ? (hand === lead ? "lead" : "rear") : null;
    const prefix = side === "lead" ? "Lead " : side === "rear" ? "Rear " : "";
    return {
      hand,
      side,
      total: h.total,
      dots: [
        {
          kind: "straight",
          label: side === "lead" ? "Jab" : side === "rear" ? "Cross" : "Straight",
          count: h.straight,
        },
        { kind: "hook", label: prefix ? `${prefix}hook` : "Hook", count: h.hook },
        { kind: "uppercut", label: prefix ? `${prefix}uppercut` : "Uppercut", count: h.uppercut },
      ],
      unnamed: Math.max(0, h.total - h.straight - h.hook - h.uppercut),
    };
  });
}

/** The breakdown of the camera with the most punches — it speaks for the fighter,
 *  as its count already does. */
export function leadingTally(
  cams: { punches: number; tally?: PunchTally | null }[],
): PunchTally | null {
  let best: { punches: number; tally?: PunchTally | null } | null = null;
  for (const c of cams) if (c.tally && (!best || c.punches > best.punches)) best = c;
  return best?.tally ?? null;
}

import type { ProtocolBlockSpec } from "@/lib/api";

/** How long a recording category runs at the default pace — "30 punches · about
 *  50 s", "2 min" — so the coach knows what they're starting. */
export function categoryLength(spec: ProtocolBlockSpec): string {
  if (spec.duration_s) return `${Math.round(spec.duration_s / 60)} min`;
  if (!spec.reps) return "";
  const pace = spec.pace_s ?? 1.5;
  const seconds = 1 + (spec.reps - 1) * pace + 2;
  const unit = spec.kind === "combo" ? "combinations" : "punches";
  return `${spec.reps} ${unit} · about ${Math.round(seconds / 5) * 5} s`;
}

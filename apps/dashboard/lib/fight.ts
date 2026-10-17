/**
 * Small helpers for the fight card and the tale of the tape (ADR-069): names for
 * divisions and belts, and the units a broadcast shows (kg + lb, cm + ft/in).
 */

import type { BeltOnTheLine, Bout, FightType } from "@/lib/api";

export const LB_PER_KG = 2.20462;

export const FIGHT_TYPE_LABEL: Record<FightType, string> = {
  pro_title: "Title fight",
  pro: "Professional",
  amateur: "Amateur",
  exhibition: "Exhibition",
  sparring: "Sparring (friendly)",
};

export const TITLE_KIND_LABEL: Record<string, string> = {
  world: "World",
  super: "Super",
  regular: "Regular",
  interim: "Interim",
  eliminator: "Eliminator",
  regional: "Regional",
  other: "Other",
};

export function weightClassLabel(key: string | null | undefined): string {
  if (!key) return "";
  return key
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ")
    .replace("Super ", "Super-")
    .replace("Light ", "Light-");
}

export function kgLb(kg: number | null | undefined): string | null {
  if (kg == null) return null;
  return `${kg.toFixed(1)} kg · ${(kg * LB_PER_KG).toFixed(1)} lb`;
}

export function cmFtIn(cm: number | null | undefined): string | null {
  if (cm == null) return null;
  const inches = cm / 2.54;
  const ft = Math.floor(inches / 12);
  const rest = Math.round(inches - ft * 12);
  return `${Math.round(cm)} cm · ${rest === 12 ? ft + 1 : ft}′${rest === 12 ? 0 : rest}″`;
}

export function cmIn(cm: number | null | undefined): string | null {
  if (cm == null) return null;
  return `${Math.round(cm)} cm · ${Math.round(cm / 2.54)}″`;
}

export function ageFrom(dob: string | null | undefined, on: Date = new Date()): number | null {
  if (!dob) return null;
  const d = new Date(dob);
  if (Number.isNaN(d.getTime())) return null;
  let age = on.getFullYear() - d.getFullYear();
  const before = on.getMonth() < d.getMonth() || (on.getMonth() === d.getMonth() && on.getDate() < d.getDate());
  if (before) age -= 1;
  return age;
}

export function beltLabel(t: BeltOnTheLine): string {
  return t.kind === "world" ? `${t.body} world` : `${t.body} ${TITLE_KIND_LABEL[t.kind]?.toLowerCase() ?? t.kind}`;
}

/** "WBC world · IBF world" — or the fight type for a non-title fight. */
export function whatsAtStake(b: Pick<Bout, "fight_type" | "titles">): string {
  if (b.fight_type === "pro_title" && b.titles.length) return b.titles.map(beltLabel).join(" · ");
  return FIGHT_TYPE_LABEL[b.fight_type] ?? b.fight_type;
}

/** Made weight? null when there's no limit (heavyweight) or no weigh-in yet. */
export function madeWeight(weighInKg: number | null, limitKg: number | null): boolean | null {
  if (weighInKg == null || limitKg == null) return null;
  return weighInKg <= limitKg + 1e-9;
}

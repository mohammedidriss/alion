"use client";

/**
 * Tale of the tape (ADR-069) — the two fighters side by side, as a broadcast shows
 * them: record, age, nationality, stance, height, reach, weight, division, belts
 * held, gym, and the fight's official weigh-in against the limit.
 *
 * The facts come from each fighter's profile. With `onFighterSaved`, any of them
 * can be filled in or corrected right here — a missing reach shows an amber "add"
 * — and the change is saved to the profile. Weigh-ins belong to the fight, not the
 * profile: they're edited through `onWeighIn`.
 */

import { useState } from "react";
import { api, type Fighter, type FighterTitle, type Stance } from "@/lib/api";
import { ageFrom, cmFtIn, cmIn, kgLb, madeWeight, weightClassLabel } from "@/lib/fight";

type Corner = "red" | "blue";

interface Props {
  red: Fighter | null;
  blue: Fighter | null;
  redTitles?: FighterTitle[];
  blueTitles?: FighterTitle[];
  weighIn?: { red: number | null; blue: number | null };
  limitKg?: number | null;
  onWeighIn?: (corner: Corner, kg: number | null) => void;
  onFighterSaved?: (f: Fighter) => void;
}

type Kind = "text" | "number" | "date" | "stance" | "record" | "readonly";

interface Row {
  label: string;
  kind: Kind;
  show: (f: Fighter, corner: Corner) => string | null;
  value?: (f: Fighter) => string; // what the editor starts from
  patch?: (raw: string, f: Fighter) => Partial<Fighter> | null; // null = invalid
}

const num = (raw: string, lo: number, hi: number): number | null => {
  const v = Number.parseFloat(raw);
  return Number.isFinite(v) && v >= lo && v <= hi ? v : null;
};

const ROWS: Row[] = [
  {
    label: "Record",
    kind: "record",
    show: (f) =>
      `${f.record_wins}-${f.record_losses}-${f.record_draws}` +
      (f.record_kos ? ` · ${f.record_kos} KO` : "") +
      (f.record_wins + f.record_losses + f.record_draws === 0 ? " · debut" : ""),
    value: (f) => `${f.record_wins} ${f.record_losses} ${f.record_draws} ${f.record_kos}`,
    patch: (raw) => {
      const parts = raw.trim().split(/[\s,\-/]+/).map((x) => Number.parseInt(x, 10));
      if (parts.length < 3 || parts.some((x) => !Number.isFinite(x) || x < 0)) return null;
      const [w, l, d, ko = 0] = parts;
      if (ko > w) return null;
      return { record_wins: w, record_losses: l, record_draws: d, record_kos: ko };
    },
  },
  {
    label: "Age",
    kind: "date",
    show: (f) => {
      const a = ageFrom(f.dob);
      return a == null ? null : `${a}`;
    },
    value: (f) => f.dob ?? "",
    patch: (raw) => (raw ? { dob: raw } : null),
  },
  {
    label: "Nationality",
    kind: "text",
    show: (f) => f.nationality || null,
    value: (f) => f.nationality ?? "",
    patch: (raw) => (raw.trim() ? { nationality: raw.trim() } : null),
  },
  {
    label: "Stance",
    kind: "stance",
    show: (f) => (f.stance ? f.stance.charAt(0).toUpperCase() + f.stance.slice(1) : null),
    value: (f) => f.stance,
    patch: (raw) => ({ stance: raw as Stance }),
  },
  {
    label: "Height",
    kind: "number",
    show: (f) => cmFtIn(f.height_cm),
    value: (f) => (f.height_cm != null ? String(f.height_cm) : ""),
    patch: (raw) => {
      const v = num(raw, 80, 250);
      return v == null ? null : { height_cm: v };
    },
  },
  {
    label: "Reach",
    kind: "number",
    show: (f) => cmIn(f.reach_cm),
    value: (f) => (f.reach_cm != null ? String(f.reach_cm) : ""),
    patch: (raw) => {
      const v = num(raw, 80, 260);
      return v == null ? null : { reach_cm: v };
    },
  },
  {
    label: "Weight",
    kind: "number",
    show: (f) => kgLb(f.weight_kg),
    value: (f) => (f.weight_kg != null ? String(f.weight_kg) : ""),
    patch: (raw) => {
      const v = num(raw, 1, 400);
      return v == null ? null : { weight_kg: v };
    },
  },
  {
    label: "Division",
    kind: "readonly",
    show: (f) => weightClassLabel(f.weight_class) || null,
  },
  {
    label: "Gym",
    kind: "text",
    show: (f) => f.gym || null,
    value: (f) => f.gym ?? "",
    patch: (raw) => (raw.trim() ? { gym: raw.trim() } : null),
  },
];

export function TaleOfTheTape({
  red,
  blue,
  redTitles = [],
  blueTitles = [],
  weighIn,
  limitKg = null,
  onWeighIn,
  onFighterSaved,
}: Props) {
  const held = (ts: FighterTitle[]) =>
    ts.filter((t) => t.status === "active").map((t) => t.name).join(" · ") || null;

  return (
    <div className="overflow-hidden rounded-2xl border border-white/10">
      <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-x-3 bg-gradient-to-r from-red-500/15 via-transparent to-sky-500/15 px-3 py-3">
        <Name f={red} corner="red" />
        <div className="pb-0.5 text-[10px] font-semibold uppercase tracking-widest text-neutral-500">
          Tale of the tape
        </div>
        <Name f={blue} corner="blue" />
      </div>
      <div className="divide-y divide-white/5">
        {ROWS.map((row) => (
          <div key={row.label} className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-3 px-3 py-1.5 text-sm">
            <Cell f={red} row={row} corner="red" onSaved={onFighterSaved} />
            <div className="w-24 text-center text-[11px] uppercase tracking-wide text-neutral-500">
              {row.label}
            </div>
            <Cell f={blue} row={row} corner="blue" onSaved={onFighterSaved} />
          </div>
        ))}
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-3 px-3 py-1.5 text-sm">
          <div className="text-right text-neutral-200">{red ? (held(redTitles) ?? "—") : ""}</div>
          <div className="w-24 text-center text-[11px] uppercase tracking-wide text-neutral-500">
            Belts held
          </div>
          <div className="text-neutral-200">{blue ? (held(blueTitles) ?? "—") : ""}</div>
        </div>
        {weighIn && (
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-3 bg-white/[0.02] px-3 py-2 text-sm">
            <WeighIn kg={weighIn.red} limitKg={limitKg} corner="red" onChange={onWeighIn} />
            <div className="w-24 text-center text-[11px] uppercase tracking-wide text-neutral-400">
              Weigh-in
            </div>
            <WeighIn kg={weighIn.blue} limitKg={limitKg} corner="blue" onChange={onWeighIn} />
          </div>
        )}
      </div>
    </div>
  );
}

function Name({ f, corner }: { f: Fighter | null; corner: Corner }) {
  const align = corner === "red" ? "text-right" : "text-left";
  const color = corner === "red" ? "text-red-300" : "text-sky-300";
  return (
    <div className={align}>
      <div className={`text-[10px] font-semibold uppercase ${color}`}>{corner} corner</div>
      <div className="truncate text-base font-semibold text-neutral-100">{f?.name ?? "—"}</div>
      {f?.nickname && <div className="truncate text-xs italic text-neutral-400">“{f.nickname}”</div>}
    </div>
  );
}

function Cell({
  f,
  row,
  corner,
  onSaved,
}: {
  f: Fighter | null;
  row: Row;
  corner: Corner;
  onSaved?: (f: Fighter) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const align = corner === "red" ? "justify-end text-right" : "justify-start text-left";
  if (!f) return <div />;
  const shown = row.show(f, corner);
  const canEdit = Boolean(onSaved && row.kind !== "readonly" && row.patch);

  const save = async () => {
    const patch = row.patch?.(draft, f);
    if (!patch) {
      setErr(row.kind === "record" ? "W L D KO, e.g. 12 1 0 8" : "check the value");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const updated = await api.updateFighter(f.id, patch);
      onSaved?.(updated);
      setEditing(false);
    } catch (e) {
      setErr(String(e).includes("403") ? "not yours to edit" : "couldn't save");
    } finally {
      setBusy(false);
    }
  };

  if (editing) {
    const common =
      "w-full max-w-[11rem] rounded-md border border-white/15 bg-black/50 px-2 py-1 text-sm text-neutral-100";
    return (
      <div className={`flex flex-col gap-0.5 ${corner === "red" ? "items-end" : "items-start"}`}>
        <div className="flex items-center gap-1">
          {row.kind === "stance" ? (
            <select value={draft} onChange={(e) => setDraft(e.target.value)} className={common}>
              <option value="orthodox">Orthodox</option>
              <option value="southpaw">Southpaw</option>
              <option value="switch">Switch</option>
            </select>
          ) : (
            <input
              autoFocus
              type={row.kind === "date" ? "date" : row.kind === "number" ? "number" : "text"}
              step={row.kind === "number" ? "0.1" : undefined}
              placeholder={
                row.kind === "record" ? "W L D KO" : row.kind === "number" ? (row.label === "Weight" ? "kg" : "cm") : ""
              }
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") save();
                if (e.key === "Escape") setEditing(false);
              }}
              className={common}
            />
          )}
          <button
            onClick={save}
            disabled={busy}
            className="rounded-md bg-emerald-500 px-2 py-1 text-xs font-semibold text-black disabled:opacity-50"
          >
            Save
          </button>
          <button onClick={() => setEditing(false)} className="px-1 text-xs text-neutral-500">
            ✕
          </button>
        </div>
        {err && <span className="text-[10px] text-red-300">{err}</span>}
      </div>
    );
  }

  return (
    <div className={`flex ${align}`}>
      {canEdit ? (
        <button
          onClick={() => {
            setDraft(row.value?.(f) ?? "");
            setErr(null);
            setEditing(true);
          }}
          className={`rounded px-1 ${shown ? "text-neutral-100 hover:bg-white/5" : "text-amber-300/90 hover:bg-amber-500/10"}`}
          title={shown ? "Edit — saved to the fighter's profile" : "Add — saved to the fighter's profile"}
        >
          {shown ?? "+ add"}
        </button>
      ) : (
        <span className={shown ? "text-neutral-100" : "text-neutral-600"}>{shown ?? "—"}</span>
      )}
    </div>
  );
}

function WeighIn({
  kg,
  limitKg,
  corner,
  onChange,
}: {
  kg: number | null;
  limitKg: number | null;
  corner: Corner;
  onChange?: (corner: Corner, kg: number | null) => void;
}) {
  const made = madeWeight(kg, limitKg);
  const align = corner === "red" ? "items-end text-right" : "items-start text-left";
  return (
    <div className={`flex flex-col ${align}`}>
      {onChange ? (
        <input
          type="number"
          step="0.1"
          min="1"
          max="400"
          placeholder="kg"
          defaultValue={kg ?? ""}
          onBlur={(e) => {
            const v = Number.parseFloat(e.target.value);
            onChange(corner, Number.isFinite(v) && v > 0 ? v : null);
          }}
          className="w-24 rounded-md border border-white/15 bg-black/50 px-2 py-1 text-sm text-neutral-100"
        />
      ) : (
        <span className="text-neutral-100">{kgLb(kg) ?? "—"}</span>
      )}
      {kg != null && onChange && <span className="text-[10px] text-neutral-500">{kgLb(kg)}</span>}
      {made === true && <span className="text-[10px] text-emerald-300">made weight</span>}
      {made === false && limitKg != null && (
        <span className="text-[10px] text-red-300">over by {(kg! - limitKg).toFixed(1)} kg</span>
      )}
    </div>
  );
}

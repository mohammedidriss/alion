"use client";

/**
 * Pupil readings (ADR-044): a pupillometer's values, entered as the device showed
 * them — eye, NPi or size, when, how bright the room was, and when in the session.
 * RingsideIQ adds no thresholds and no interpretation: what a reading means is for the
 * medical staff. Health data, like the rest of this page.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type PupilReading } from "@/lib/api";

function errorText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/^(\d{3}) ([\s\S]*)$/);
  try {
    return m ? String(JSON.parse(m[2]).detail ?? raw) : raw;
  } catch {
    return raw;
  }
}

function nowLocal(): string {
  const d = new Date();
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

export function PupilReadingsCard({ fighterId }: { fighterId: string }) {
  const [rows, setRows] = useState<PupilReading[] | null>(null);
  const [adding, setAdding] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [form, setForm] = useState({ taken_at: nowLocal(), eye: "left", npi: "", size_mm: "", light_lux: "", device: "", context: "" });

  const load = useCallback(() => {
    api
      .pupilReadings(fighterId)
      .then(setRows)
      .catch(() => setRows([]));
  }, [fighterId]);
  useEffect(() => load(), [load]);

  const num = (v: string) => (v.trim() === "" ? null : Number(v));
  const save = async () => {
    setErr(null);
    try {
      await api.addPupilReading(fighterId, {
        taken_at: new Date(form.taken_at).toISOString(),
        eye: form.eye as "left" | "right",
        npi: num(form.npi),
        size_mm: num(form.size_mm),
        light_lux: num(form.light_lux),
        device: form.device.trim() || null,
        context: form.context.trim() || null,
        session_id: null,
      });
      setAdding(false);
      setForm({ ...form, npi: "", size_mm: "", context: "" });
      load();
    } catch (e) {
      setErr(errorText(e));
    }
  };

  const input = "w-full rounded-lg border border-white/10 bg-black/30 px-2 py-1.5 text-sm outline-none focus:border-emerald-500/50";
  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">Pupil readings</h2>
          <p className="text-xs text-neutral-400">
            As the pupillometer showed them. RingsideIQ adds no thresholds and no interpretation — the
            medical staff read them.
          </p>
        </div>
        <button
          onClick={() => setAdding((v) => !v)}
          className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
        >
          {adding ? "Cancel" : "Add a reading"}
        </button>
      </div>
      {adding && (
        <div className="grid gap-2 sm:grid-cols-4">
          <label className="text-xs text-neutral-400">
            When
            <input id="pupil-when" type="datetime-local" value={form.taken_at} onChange={(e) => setForm({ ...form, taken_at: e.target.value })} className={input} />
          </label>
          <label className="text-xs text-neutral-400">
            Eye
            <select id="pupil-eye" value={form.eye} onChange={(e) => setForm({ ...form, eye: e.target.value })} className={input}>
              <option value="left">Left</option>
              <option value="right">Right</option>
            </select>
          </label>
          <label className="text-xs text-neutral-400">
            NPi (0–5)
            <input id="pupil-npi" inputMode="decimal" value={form.npi} onChange={(e) => setForm({ ...form, npi: e.target.value })} className={input} />
          </label>
          <label className="text-xs text-neutral-400">
            Size (mm)
            <input id="pupil-size" inputMode="decimal" value={form.size_mm} onChange={(e) => setForm({ ...form, size_mm: e.target.value })} className={input} />
          </label>
          <label className="text-xs text-neutral-400">
            Room light (lux, if known)
            <input id="pupil-lux" inputMode="numeric" value={form.light_lux} onChange={(e) => setForm({ ...form, light_lux: e.target.value })} className={input} />
          </label>
          <label className="text-xs text-neutral-400">
            Device
            <input id="pupil-device" value={form.device} onChange={(e) => setForm({ ...form, device: e.target.value })} placeholder="e.g. NPi-300" className={input} />
          </label>
          <label className="text-xs text-neutral-400 sm:col-span-2">
            When in the session
            <input id="pupil-context" value={form.context} onChange={(e) => setForm({ ...form, context: e.target.value })} placeholder="e.g. rest after round 3" className={input} />
          </label>
          <div className="sm:col-span-4">
            <button onClick={() => void save()} className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400">
              Save reading
            </button>
            {err && <span className="ml-2 text-sm text-red-300">{err}</span>}
          </div>
        </div>
      )}
      {rows && rows.length === 0 && !adding && <p className="text-sm text-neutral-400">No readings yet.</p>}
      {rows && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[480px] text-sm">
            <thead className="text-left text-xs uppercase text-neutral-400">
              <tr>
                <th className="py-1.5 pr-3">When</th>
                <th className="py-1.5 pr-3">Eye</th>
                <th className="py-1.5 pr-3">NPi</th>
                <th className="py-1.5 pr-3">Size</th>
                <th className="py-1.5 pr-3">Light</th>
                <th className="py-1.5">Context</th>
              </tr>
            </thead>
            <tbody className="text-neutral-200">
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-white/5">
                  <td className="py-1.5 pr-3">{new Date(r.taken_at).toLocaleString()}</td>
                  <td className="py-1.5 pr-3 capitalize">{r.eye}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{r.npi ?? "—"}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{r.size_mm != null ? `${r.size_mm} mm` : "—"}</td>
                  <td className="py-1.5 pr-3 tabular-nums">{r.light_lux != null ? `${r.light_lux} lx` : "—"}</td>
                  <td className="py-1.5 text-neutral-400">
                    {[r.context, r.device].filter(Boolean).join(" · ") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

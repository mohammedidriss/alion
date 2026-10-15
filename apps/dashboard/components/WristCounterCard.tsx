"use client";

/**
 * The wrist sensors' punch counter (ADR-060), on the AI models page: how well the
 * newest version counts each kind of block on takes it never trained on, next to
 * the detector's defaults it replaces, and a button to train a new one from every
 * take. Researchers only (the API enforces it).
 */

import { useEffect, useState } from "react";
import { api, type WristCounterReport } from "@/lib/api";

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

const BLOCKS: [string, string][] = [
  ["jab", "Jabs"],
  ["cross", "Crosses"],
  ["hook", "Hooks"],
  ["uppercut", "Uppercuts"],
  ["combo", "Combos"],
  ["negative", "No-punch block"],
];

export function WristCounterCard() {
  const [report, setReport] = useState<WristCounterReport | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .wristCounter()
      .then((r) => setReport(r.report))
      .catch(() => setReport(null))
      .finally(() => setLoaded(true));
  }, []);

  const train = async () => {
    setBusy(true);
    setMsg("Training — scoring it on takes it never sees first (about a minute)…");
    try {
      const r = await api.trainWristCounter();
      setReport(r.report);
      setMsg(
        `Version ${r.report.version} is in use: it counts the wrists live, and each session is counted again the next time it's opened.`,
      );
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      setMsg(raw.replace(/^\d{3} /, "").replace(/^\{"detail":"(.*)"\}$/, "$1"));
    } finally {
      setBusy(false);
    }
  };

  const c = report?.held_out_takes.counter;
  const d = report?.held_out_takes.detector;
  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-xs font-medium uppercase tracking-wider text-neutral-500">Training &amp; score</h3>
        <button
          onClick={train}
          disabled={busy}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          {busy ? "Training…" : report ? "Train again" : "Train"}
        </button>
      </div>
      {msg && <p className="text-sm text-amber-200">{msg}</p>}
      {loaded && !report && !msg && (
        <p className="text-sm text-neutral-300">
          Not trained yet — the wrists count with the detector&apos;s fixed settings, which suit
          straights but miss gentle hooks and count an uppercut&apos;s return to guard as a punch.
        </p>
      )}
      {report && c && d && (
        <div className="space-y-2 text-sm">
          <p className="text-neutral-200">
            <b>Version {report.version}</b> · {new Date(report.created_at).toLocaleString()} ·{" "}
            {report.data.punches.toLocaleString()} labelled punches from {report.data.takes} takes,{" "}
            {report.data.participants} participant{report.data.participants === 1 ? "" : "s"}
          </p>
          <div className="rounded-xl bg-white/5 p-3">
            <div className="text-xs text-neutral-400">On takes it never trained on (F1)</div>
            <div className="text-2xl font-bold text-emerald-400">
              {pct(c.f1)} <span className="text-base font-normal text-neutral-400">vs {pct(d.f1)} fixed settings</span>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-xs">
              <thead className="text-left text-[10px] uppercase tracking-wide text-neutral-500">
                <tr>
                  <th className="py-1.5 pr-3 font-normal">Block</th>
                  <th className="py-1.5 pr-3 font-normal">Labelled</th>
                  <th className="py-1.5 pr-3 font-normal">Fixed settings</th>
                  <th className="py-1.5 font-normal">Counter</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {BLOCKS.filter(([k]) => c.by_block[k]).map(([k, title]) => {
                  const cb = c.by_block[k];
                  const db = d.by_block[k];
                  const idle = k === "negative";
                  return (
                    <tr key={k} className="text-neutral-200">
                      <td className="py-1.5 pr-3">{title}</td>
                      <td className="py-1.5 pr-3 tabular-nums">{idle ? 0 : cb.labelled}</td>
                      <td className="py-1.5 pr-3 tabular-nums">
                        {idle ? `${db.on_idle_wrist} false` : `${db.found} · ${pct(db.f1)}`}
                      </td>
                      <td className="py-1.5 tabular-nums">
                        {idle ? `${cb.on_idle_wrist} false` : `${cb.found} · ${pct(cb.f1)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-neutral-500">
            Found · F1 on the punching wrist; the no-punch block shows punches counted where none
            were thrown. Free shadowboxing isn&apos;t scored — its labels come from the fixed settings.
          </p>
          {report.data.participants < 3 && (
            <p className="text-xs text-amber-300">
              Trained on {report.data.participants} participant
              {report.data.participants === 1 ? "" : "s"}: expect it to do worse on other fighters
              until their takes are in.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

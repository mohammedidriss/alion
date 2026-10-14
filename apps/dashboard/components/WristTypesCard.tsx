"use client";

/**
 * The wrist sensors' punch-type model (ADR-029), on the Datasets page: how well
 * the newest version names straights, hooks and uppercuts on recordings it never
 * trained on, and a button to train a new one from every take. Researchers only
 * (the API enforces it).
 */

import { useEffect, useState } from "react";
import { api, type WristTypesReport } from "@/lib/api";

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export function WristTypesCard() {
  const [report, setReport] = useState<WristTypesReport | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .wristTypes()
      .then((r) => setReport(r.report))
      .catch(() => setReport(null))
      .finally(() => setLoaded(true));
  }, []);

  const train = async () => {
    setBusy(true);
    setMsg("Training — scoring it on takes it never sees first (under a minute)…");
    try {
      const r = await api.trainWristTypes();
      setReport(r.report);
      setMsg(
        `Version ${r.report.version} is in use. Each session's punches are named again the next time it's opened.`,
      );
    } catch (e) {
      const raw = e instanceof Error ? e.message : String(e);
      setMsg(raw.replace(/^\d{3} /, "").replace(/^\{"detail":"(.*)"\}$/, "$1"));
    } finally {
      setBusy(false);
    }
  };

  const h = report?.held_out_takes;
  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">Punch types from the wrist sensors</h2>
          <p className="text-xs text-neutral-400">
            Names each punch straight, hook or uppercut from the wrists alone (jab or cross from
            the hand and the stance), shown on every session&apos;s per-round breakdown.
          </p>
        </div>
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
          Not trained yet — sessions don&apos;t show punch types from the wrists until it is.
        </p>
      )}
      {report && h && (
        <div className="space-y-2 text-sm">
          <p className="text-neutral-200">
            <b>Version {report.version}</b> · {new Date(report.created_at).toLocaleString()} ·{" "}
            {report.data.punches.toLocaleString()} punches from {report.data.takes} takes,{" "}
            {report.data.participants} participant{report.data.participants === 1 ? "" : "s"}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-xl bg-white/5 p-3">
              <div className="text-xs text-neutral-400">On takes it never trained on</div>
              <div className="text-2xl font-bold text-emerald-400">{pct(h.accuracy)}</div>
              <div className="text-xs text-neutral-400">
                (always guessing the commonest: {pct(h.majority_share)}) · straight {pct(h.recall.straight)} ·
                hook {pct(h.recall.hook)} · uppercut {pct(h.recall.uppercut)}
              </div>
            </div>
            {report.combos && (
              <div className="rounded-xl bg-white/5 p-3">
                <div className="text-xs text-neutral-400">Combinations (trained on single-type blocks)</div>
                <div className="text-2xl font-bold text-emerald-400">{pct(report.combos.accuracy)}</div>
                <div className="text-xs text-neutral-400">{report.combos.punches} punches</div>
              </div>
            )}
            {report.other_boxers && (
              <div className="rounded-xl bg-white/5 p-3 sm:col-span-2">
                <div className="text-xs text-neutral-400">Other boxers it never saw ({report.other_boxers.dataset})</div>
                <div className="text-2xl font-bold text-amber-300">{pct(report.other_boxers.accuracy)}</div>
                <div className="text-xs text-neutral-400">
                  {report.other_boxers.punches} punches · straight {pct(report.other_boxers.recall.straight)} · hook{" "}
                  {pct(report.other_boxers.recall.hook)} · uppercut {pct(report.other_boxers.recall.uppercut)} — what
                  to expect for a new fighter until their takes are in.
                </div>
              </div>
            )}
          </div>
          {report.data.participants < 3 && (
            <p className="text-xs text-amber-300">
              Trained on {report.data.participants} participant
              {report.data.participants === 1 ? "" : "s"}
              {Object.keys(report.data.stances).length === 1 && `, ${Object.keys(report.data.stances)[0]} only`}
              : expect it to do worse on other fighters until their takes are in.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

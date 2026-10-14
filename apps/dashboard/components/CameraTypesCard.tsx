"use client";

/**
 * The cameras' punch-type model (ADR-034), on the Datasets page: how well the
 * newest version names straights, hooks and uppercuts from the arm's 3D motion
 * on takes it never trained on — one camera at a time, and with all the take's
 * cameras together — and a button to train a new one. Researchers only (the API
 * enforces it).
 */

import { useEffect, useState } from "react";
import { api, type CameraTypesReport } from "@/lib/api";

const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export function CameraTypesCard() {
  const [report, setReport] = useState<CameraTypesReport | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api
      .cameraTypes()
      .then((r) => setReport(r.report))
      .catch(() => setReport(null))
      .finally(() => setLoaded(true));
  }, []);

  const train = async () => {
    setBusy(true);
    setMsg("Training — reading every take's camera pose and scoring on takes it never sees first (a minute or two)…");
    try {
      const r = await api.trainCameraTypes();
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

  const v = report?.held_out_views;
  const p = report?.held_out_punches;
  return (
    <div className="card space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold">Punch types from the cameras</h2>
          <p className="text-xs text-neutral-400">
            Names each punch from the arm&apos;s 3D motion after a session. Two or more cameras that saw
            it decide together; with one camera the wrist sensor joins in; with none the wrist names it alone.
            Live, the camera boxes show counts only.
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
          Not trained yet — sessions name punch types from the wrists alone until it is.
        </p>
      )}
      {report && v && p && (
        <div className="space-y-2 text-sm">
          <p className="text-neutral-200">
            <b>Version {report.version}</b> · {new Date(report.created_at).toLocaleString()} ·{" "}
            {report.data.punches.toLocaleString()} punches ({report.data.views.toLocaleString()} camera views) from{" "}
            {report.data.takes} takes, {report.data.participants} participant
            {report.data.participants === 1 ? "" : "s"}
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="rounded-xl bg-white/5 p-3">
              <div className="text-xs text-neutral-400">All the take&apos;s cameras together, takes it never trained on</div>
              <div className="text-2xl font-bold text-emerald-400">{pct(p.accuracy)}</div>
              <div className="text-xs text-neutral-400">
                straight {pct(p.recall.straight)} · hook {pct(p.recall.hook)} · uppercut {pct(p.recall.uppercut)}
              </div>
            </div>
            <div className="rounded-xl bg-white/5 p-3">
              <div className="text-xs text-neutral-400">One camera at a time</div>
              <div className="text-2xl font-bold text-emerald-400">{pct(v.accuracy)}</div>
              <div className="text-xs text-neutral-400">
                straight {pct(v.recall.straight)} · hook {pct(v.recall.hook)} · uppercut {pct(v.recall.uppercut)}
              </div>
            </div>
          </div>
          {report.data.participants < 3 && (
            <p className="text-xs text-amber-300">
              Trained on {report.data.participants} participant{report.data.participants === 1 ? "" : "s"}: expect
              it to do worse on other fighters, camera placements and southpaws until their takes are in.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

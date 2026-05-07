"use client";

import { useEffect, useState } from "react";
import {
  api,
  type EvaluationResponse,
  type GroundTruthPunch,
} from "@/lib/api";

/**
 * Detector evaluation card — sits on the session detail page.
 *
 * Lets a coach upload a `labels.json` (ground-truth manually labeled from
 * watching the video) for THIS session, and shows precision / recall / F1
 * vs the detector's output. This is the dissertation's defensible
 * accuracy number; without real labels every other metric is uncalibrated.
 */
export function EvaluationCard({ sessionId }: { sessionId: string }) {
  const [evalRes, setEvalRes] = useState<EvaluationResponse | null>(null);
  const [labels, setLabels] = useState<GroundTruthPunch[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const [labs, ev] = await Promise.all([
        api.getLabels(sessionId),
        api.sessionEvaluation(sessionId),
      ]);
      setLabels(labs?.labels ?? null);
      setEvalRes(ev);
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const onUploadFile = async (file: File) => {
    setBusy(true);
    setErr(null);
    try {
      const text = await file.text();
      const parsed = JSON.parse(text);
      if (!Array.isArray(parsed)) {
        throw new Error(
          "labels.json must be a JSON array of {t_ms, hand, punch_type?}",
        );
      }
      await api.putLabels(sessionId, parsed);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const onClearLabels = async () => {
    if (!confirm("Delete all labels for this session?")) return;
    setBusy(true);
    try {
      await api.deleteLabels(sessionId);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!evalRes) {
    return (
      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">Detector evaluation</h2>
        <p className="mt-2 text-sm text-neutral-500">Loading…</p>
      </section>
    );
  }

  return (
    <section className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium text-violet-200">Detector evaluation</h2>
        <span className="text-[10px] uppercase tracking-wider text-violet-300/70">
          ground-truth labels vs detector
        </span>
      </div>
      <p className="mt-1 text-xs text-neutral-400">
        The dissertation&apos;s defensible accuracy number. Watch the video,
        manually mark each punch&apos;s timestamp + hand + type, and upload a{" "}
        <code className="rounded bg-black/30 px-1">labels.json</code> here.
      </p>

      {err && (
        <p className="mt-3 rounded-xl border border-red-500/30 bg-red-950/30 p-2 text-xs text-red-200">
          {err}
        </p>
      )}

      {!evalRes.has_labels ? (
        <div className="mt-4 space-y-3">
          <div className="rounded-xl border border-dashed border-violet-500/30 p-3 text-xs text-neutral-400">
            <p className="font-medium text-neutral-200">
              No labels uploaded yet.
            </p>
            <p className="mt-1">
              {evalRes.detection_count} detections exist; until labels are
              attached the detector&apos;s accuracy on this session is
              unmeasured.
            </p>
            <p className="mt-2 text-[11px] text-neutral-500">
              Format: a JSON array of{" "}
              <code className="rounded bg-black/30 px-1">
                {`{ t_ms: number, hand: "left" | "right", punch_type?: "jab" | "cross" | "hook" | "uppercut" }`}
              </code>
              . `t_ms` is milliseconds since session start.
            </p>
          </div>
          <input
            type="file"
            accept="application/json,.json"
            disabled={busy}
            onChange={(e) =>
              e.target.files?.[0] && onUploadFile(e.target.files[0])
            }
            className="text-xs"
          />
        </div>
      ) : (
        <>
          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric
              label="Precision"
              value={(evalRes.precision * 100).toFixed(1)}
              unit="%"
              tone={evalRes.precision >= 0.8 ? "good" : evalRes.precision >= 0.5 ? "ok" : "bad"}
            />
            <Metric
              label="Recall"
              value={(evalRes.recall * 100).toFixed(1)}
              unit="%"
              tone={evalRes.recall >= 0.8 ? "good" : evalRes.recall >= 0.5 ? "ok" : "bad"}
            />
            <Metric
              label="F1"
              value={evalRes.f1.toFixed(3)}
              tone={evalRes.f1 >= 0.8 ? "good" : evalRes.f1 >= 0.5 ? "ok" : "bad"}
            />
            <Metric
              label="Mean Δt"
              value={evalRes.mean_temporal_offset_ms.toFixed(0)}
              unit="ms"
            />
          </div>

          <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
            <Counter label="True positives" value={evalRes.true_positives} tone="emerald" />
            <Counter
              label="False positives"
              value={evalRes.false_positives}
              tone="red"
              hint="hallucinated detections"
            />
            <Counter
              label="False negatives"
              value={evalRes.false_negatives}
              tone="amber"
              hint="missed punches"
            />
          </div>

          {evalRes.confusion && (
            <ConfusionMatrix
              confusion={evalRes.confusion}
              classes={evalRes.classes}
            />
          )}

          <p className="mt-3 text-[11px] text-neutral-500">
            {evalRes.label_count} ground-truth labels · {evalRes.detection_count}{" "}
            detections · matching tolerance ±{evalRes.tolerance_ms.toFixed(0)} ms.
          </p>

          <div className="mt-3 flex gap-2 text-xs">
            <a
              href={`data:application/json;charset=utf-8,${encodeURIComponent(JSON.stringify(labels ?? [], null, 2))}`}
              download={`alion-${sessionId}-labels.json`}
              className="rounded-lg border border-white/5 bg-white/[0.03] px-2.5 py-1 hover:bg-white/[0.07]"
            >
              Download labels
            </a>
            <label className="cursor-pointer rounded-lg border border-white/5 bg-white/[0.03] px-2.5 py-1 hover:bg-white/[0.07]">
              Replace labels
              <input
                type="file"
                accept="application/json,.json"
                disabled={busy}
                onChange={(e) =>
                  e.target.files?.[0] && onUploadFile(e.target.files[0])
                }
                className="hidden"
              />
            </label>
            <button
              onClick={onClearLabels}
              disabled={busy}
              className="rounded-lg border border-red-500/20 bg-red-500/5 px-2.5 py-1 text-red-300 hover:bg-red-500/10"
            >
              Clear labels
            </button>
          </div>
        </>
      )}
    </section>
  );
}

function Metric({
  label,
  value,
  unit,
  tone = "neutral",
}: {
  label: string;
  value: string;
  unit?: string;
  tone?: "good" | "ok" | "bad" | "neutral";
}) {
  const color = {
    good: "text-emerald-300",
    ok: "text-amber-300",
    bad: "text-red-300",
    neutral: "text-neutral-200",
  }[tone];
  return (
    <div className="rounded-xl border border-white/5 bg-black/20 p-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className="mt-1 flex items-baseline gap-1">
        <span className={`text-2xl font-semibold tabular-nums ${color}`}>
          {value}
        </span>
        {unit && <span className="text-xs text-neutral-500">{unit}</span>}
      </div>
    </div>
  );
}

function Counter({
  label,
  value,
  tone,
  hint,
}: {
  label: string;
  value: number;
  tone: "emerald" | "red" | "amber";
  hint?: string;
}) {
  const ringColor = {
    emerald: "border-emerald-500/40 bg-emerald-500/5 text-emerald-200",
    red: "border-red-500/40 bg-red-500/5 text-red-200",
    amber: "border-amber-500/40 bg-amber-500/5 text-amber-200",
  }[tone];
  return (
    <div className={`rounded-xl border ${ringColor} p-2`}>
      <div className="text-[10px] uppercase tracking-wide opacity-70">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums">{value}</div>
      {hint && <div className="text-[10px] opacity-60">{hint}</div>}
    </div>
  );
}

function ConfusionMatrix({
  confusion,
  classes,
}: {
  confusion: Record<string, Record<string, number>>;
  classes: string[];
}) {
  const rows = [...classes, "unlabeled"];
  return (
    <div className="mt-4">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        Punch-type confusion (truth → predicted)
      </div>
      <table className="mt-2 w-full text-xs">
        <thead>
          <tr className="text-neutral-500">
            <th className="px-2 py-1 text-left">truth ╲ pred</th>
            {rows.map((c) => (
              <th key={c} className="px-2 py-1 text-right">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r} className="border-t border-white/5">
              <td className="px-2 py-1 font-medium text-neutral-300">{r}</td>
              {rows.map((c) => {
                const v = confusion[r]?.[c] ?? 0;
                const onDiagonal = r === c && r !== "unlabeled";
                return (
                  <td
                    key={c}
                    className={`px-2 py-1 text-right tabular-nums ${
                      onDiagonal && v > 0
                        ? "font-semibold text-emerald-300"
                        : v > 0
                          ? "text-red-300/80"
                          : "text-neutral-600"
                    }`}
                  >
                    {v}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

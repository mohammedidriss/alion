"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  type ReprocessResponse,
  type SessionStatus,
} from "@/lib/api";

interface Props {
  sessionId: string;
  status: SessionStatus;
}

/**
 * Side-by-side detector comparison.
 *
 * - Live heuristic: the punch_event rows the live capture wrote.
 * - Offline second-pass: LSTM (or stricter-heuristic fallback) re-run
 *   on the saved pose parquet.
 * - Consensus: events both detectors agreed on within ±120 ms.
 *
 * Auto-fires the offline pass once when the session first reaches
 * `completed`. Manual rerun via the button below.
 */
export function DetectorComparisonCard({ sessionId, status }: Props) {
  const [result, setResult] = useState<ReprocessResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const autoFiredRef = useRef(false);

  const run = async () => {
    setLoading(true);
    setErr(null);
    try {
      setResult(await api.reprocessOffline(sessionId));
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (status === "completed" && !autoFiredRef.current && !result) {
      autoFiredRef.current = true;
      run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <section className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium text-violet-200">Detector comparison</h2>
        <span className="text-[11px] text-neutral-500">
          live + offline + consensus
        </span>
      </div>

      {status !== "completed" ? (
        <p className="mt-2 text-xs text-neutral-400">
          Runs the LSTM offline pass on the saved pose parquet once the
          session finishes. Compares live (heuristic) vs offline events
          and reconciles into a consensus stream.
        </p>
      ) : loading && !result ? (
        <p className="mt-2 text-xs text-violet-300/80">
          Replaying parquet through the second-pass detector…
        </p>
      ) : null}

      {err && <p className="mt-2 text-xs text-red-300">{err}</p>}

      {result && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-3 gap-2">
            <DetCard
              tone="emerald"
              label="Live (heuristic)"
              count={result.live_count}
              hint={`real-time during capture`}
            />
            <DetCard
              tone="amber"
              label={`Offline (${result.second_pass_name})`}
              count={result.offline_count}
              hint="post-capture LSTM"
            />
            <DetCard
              tone="violet"
              label="Consensus"
              count={result.consensus_count}
              hint={`both detectors agreed`}
            />
          </div>

          {/* Reconciliation breakdown */}
          <div className="rounded-xl border border-white/5 bg-black/30 p-3 text-xs text-neutral-300">
            <div className="mb-1 text-[10px] uppercase tracking-wide text-neutral-500">
              Reconciled stream
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span>
                ✓ both:{" "}
                <strong className="text-violet-200">{result.consensus_count}</strong>
              </span>
              <span>
                live only:{" "}
                <strong className="text-emerald-200">{result.live_only}</strong>
              </span>
              <span>
                offline only:{" "}
                <strong className="text-amber-200">{result.offline_only}</strong>
              </span>
            </div>
            <p className="mt-2 text-[11px] text-neutral-500">
              Consensus = events both detectors fired within ±120 ms of
              each other. Use this for high-precision metrics; use the
              union for max recall.
            </p>
          </div>

          <div className="flex justify-end">
            <button
              onClick={run}
              disabled={loading}
              className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-300 hover:bg-white/[0.07] disabled:opacity-50"
            >
              {loading ? "rerunning…" : "rerun offline pass"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function DetCard({
  tone,
  label,
  count,
  hint,
}: {
  tone: "emerald" | "amber" | "violet";
  label: string;
  count: number;
  hint: string;
}) {
  const ring = {
    emerald: "border-emerald-500/30 bg-emerald-500/5",
    amber: "border-amber-500/30 bg-amber-500/5",
    violet: "border-violet-500/30 bg-violet-500/5",
  }[tone];
  const big = {
    emerald: "text-emerald-200",
    amber: "text-amber-200",
    violet: "text-violet-200",
  }[tone];
  return (
    <div className={`rounded-xl border ${ring} p-3`}>
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${big}`}>
        {count}
      </div>
      <div className="text-[10px] text-neutral-500">{hint}</div>
    </div>
  );
}

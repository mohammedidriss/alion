"use client";

import { useEffect, useRef, useState } from "react";
import {
  api,
  type CoachAdviceResponse,
  type PayloadMode,
  type SessionStatus,
} from "@/lib/api";

interface Props {
  sessionId: string;
  status: SessionStatus;
  /** Number of rounds that have finished so far (0 = none yet). */
  completedRounds?: number;
}

const MODE_LABEL: Record<PayloadMode, string> = {
  cv: "CV only",
  hrv: "HRV only",
  imu: "IMU only",
  fused: "Fused (CV + HRV + IMU)",
};

/**
 * Live advice card — generates corner advice progressively as each
 * round ends during live capture. After round 1, the coach gives
 * feedback on round 1. After round 2, on rounds 1-2. And so on.
 * Also auto-generates on session completion as before.
 */
export function LiveAdviceCard({
  sessionId,
  status,
  completedRounds = 0,
}: Props) {
  const [mode, setMode] = useState<PayloadMode>("fused");
  const [advice, setAdvice] = useState<CoachAdviceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Track how many rounds we've already generated advice for so we
  // only fire once per round transition, not on every re-render.
  const advisedRoundsRef = useRef(0);
  const autoFiredRef = useRef(false);
  // Track which round the current advice covers.
  const [adviceRound, setAdviceRound] = useState<number>(0);

  const generate = async (m: PayloadMode = mode) => {
    setLoading(true);
    setErr(null);
    try {
      const result = await api.generateAdvice(sessionId, m);
      setAdvice(result);
      setMode(m);
      setAdviceRound(completedRounds);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  // Auto-generate after each round ends during live capture.
  useEffect(() => {
    const isLive = status === "capturing" || status === "processing";
    if (
      isLive &&
      completedRounds > 0 &&
      completedRounds > advisedRoundsRef.current &&
      !loading
    ) {
      advisedRoundsRef.current = completedRounds;
      generate("fused");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [completedRounds, status]);

  // Also fire once when the session reaches `completed` (final summary).
  useEffect(() => {
    if (status === "completed" && !autoFiredRef.current) {
      autoFiredRef.current = true;
      generate("fused");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const isLive = status === "capturing" || status === "processing";

  return (
    <section className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium text-emerald-200">AI corner advice</h2>
        <span className="text-[11px] text-neutral-500">
          payload: {MODE_LABEL[mode]}
        </span>
      </div>

      {/* Status line */}
      {isLive && completedRounds === 0 && !advice && (
        <p className="mt-2 text-xs text-neutral-400">
          Waiting for the first round to finish — advice will generate
          automatically after each round.
        </p>
      )}
      {isLive && loading && (
        <p className="mt-2 text-xs text-emerald-300/80">
          Generating advice after round {completedRounds}…
        </p>
      )}
      {status !== "completed" && !isLive && !advice && (
        <p className="mt-2 text-xs text-neutral-400">
          Auto-generates as soon as the session finishes capture. You
          can also generate any time below.
        </p>
      )}
      {status === "completed" && loading && !advice && (
        <p className="mt-2 text-xs text-emerald-300/80">
          Generating final advice from the fused {`{CV, HRV, IMU}`} payload…
        </p>
      )}

      {advice && (
        <div className="mt-3 space-y-3">
          {/* Badge showing what round(s) this advice covers */}
          {isLive && adviceRound > 0 && (
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                After round {adviceRound}
              </span>
              {loading && (
                <span className="text-[10px] text-emerald-300/60 animate-pulse">
                  updating…
                </span>
              )}
            </div>
          )}
          <p className="text-sm text-neutral-100">{advice.summary}</p>
          {advice.action_items.length > 0 && (
            <ul className="space-y-1.5">
              {advice.action_items.map((a, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-lg border border-white/5 bg-black/30 p-2 text-xs text-neutral-200"
                >
                  <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/20 text-[10px] font-bold text-emerald-300">
                    {i + 1}
                  </span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {err && <p className="mt-2 text-xs text-red-300">{err}</p>}

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        {(["fused", "cv", "hrv", "imu"] as PayloadMode[]).map((m) => (
          <button
            key={m}
            onClick={() => generate(m)}
            disabled={loading}
            className={`rounded-full px-2.5 py-1 text-[11px] ${
              mode === m
                ? "bg-emerald-500 text-black"
                : "border border-white/10 bg-white/[0.03] text-neutral-300 hover:bg-white/[0.07]"
            } disabled:opacity-50`}
          >
            {m}
          </button>
        ))}
        <span className="ml-auto text-[11px] text-neutral-500">
          {loading ? "thinking…" : advice ? "regenerate ↺" : "click a mode"}
        </span>
      </div>
    </section>
  );
}

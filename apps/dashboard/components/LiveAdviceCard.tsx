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
}

const MODE_LABEL: Record<PayloadMode, string> = {
  cv: "CV only",
  hrv: "HRV only",
  imu: "IMU only",
  fused: "Fused (CV + HRV + IMU)",
};

/**
 * Live advice card — auto-generates corner advice as soon as the
 * session transitions to `completed`. Renders summary + action items
 * with a payload-mode toggle and a regenerate button. Sits in the
 * right column of the session page.
 */
export function LiveAdviceCard({ sessionId, status }: Props) {
  const [mode, setMode] = useState<PayloadMode>("fused");
  const [advice, setAdvice] = useState<CoachAdviceResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const autoFiredRef = useRef(false);

  const generate = async (m: PayloadMode = mode) => {
    setLoading(true);
    setErr(null);
    try {
      setAdvice(await api.generateAdvice(sessionId, m));
      setMode(m);
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };

  // Fire once when the session first reaches `completed`.
  useEffect(() => {
    if (status === "completed" && !autoFiredRef.current && !advice) {
      autoFiredRef.current = true;
      generate("fused");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  return (
    <section className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium text-emerald-200">AI corner advice</h2>
        <span className="text-[11px] text-neutral-500">
          payload: {MODE_LABEL[mode]}
        </span>
      </div>

      {status !== "completed" ? (
        <p className="mt-2 text-xs text-neutral-400">
          Auto-generates as soon as the session finishes capture. You
          can also generate any time below.
        </p>
      ) : loading && !advice ? (
        <p className="mt-2 text-xs text-emerald-300/80">
          Generating advice from the fused {`{CV, HRV, IMU}`} payload…
        </p>
      ) : null}

      {advice && (
        <div className="mt-3 space-y-3">
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

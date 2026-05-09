"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type CoachAdviceResponse, type PayloadMode } from "@/lib/api";

interface Props {
  sessionId: string;
}

const MODES: PayloadMode[] = ["cv", "hrv", "imu", "fused"];
const CRITERIA = ["specificity", "actionability", "correctness", "novelty"] as const;
type Criterion = (typeof CRITERIA)[number];

/**
 * RQ1 instrument — generates corner advice in 4 payload modes (CV, HRV,
 * IMU, fused) so a blinded coach-rater can score each on a 1–5 Likert
 * across specificity, actionability, correctness, novelty. Order is
 * randomized per session so the rater can't tell which payload produced
 * which response. Ratings persist in localStorage per (rater, session).
 */
export function RQ1RaterCard({ sessionId }: Props) {
  const [raterId, setRaterId] = useState("");
  const [variants, setVariants] = useState<Record<PayloadMode, CoachAdviceResponse | null>>({
    cv: null,
    hrv: null,
    imu: null,
    fused: null,
  });
  const [generating, setGenerating] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ratings, setRatings] = useState<
    Record<PayloadMode, Partial<Record<Criterion, number>>>
  >({ cv: {}, hrv: {}, imu: {}, fused: {} });
  const [revealed, setRevealed] = useState(false);

  // Stable per-session shuffle so the labels A/B/C/D are blinded.
  const order = useMemo<PayloadMode[]>(() => {
    const seed = Array.from(sessionId).reduce((a, c) => a + c.charCodeAt(0), 0);
    const rng = mulberry32(seed);
    const arr = [...MODES];
    for (let i = arr.length - 1; i > 0; i--) {
      const j = Math.floor(rng() * (i + 1));
      [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
  }, [sessionId]);

  const storageKey = (rater: string) =>
    `rq1:${rater || "anon"}:${sessionId}`;

  useEffect(() => {
    setRaterId(localStorage.getItem("rq1:rater") ?? "");
  }, []);

  useEffect(() => {
    const raw = localStorage.getItem(storageKey(raterId));
    if (raw) {
      try {
        setRatings(JSON.parse(raw));
      } catch {
        // ignore
      }
    } else {
      setRatings({ cv: {}, hrv: {}, imu: {}, fused: {} });
    }
    setRevealed(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [raterId, sessionId]);

  const generateAll = async () => {
    setGenerating(true);
    setErr(null);
    try {
      const next: typeof variants = { cv: null, hrv: null, imu: null, fused: null };
      for (const m of MODES) {
        next[m] = await api.generateAdvice(sessionId, m);
      }
      setVariants(next);
    } catch (e) {
      setErr(String(e));
    } finally {
      setGenerating(false);
    }
  };

  const setScore = (mode: PayloadMode, c: Criterion, value: number) => {
    setRatings((prev) => {
      const upd = { ...prev, [mode]: { ...prev[mode], [c]: value } };
      localStorage.setItem(storageKey(raterId), JSON.stringify(upd));
      return upd;
    });
  };

  const exportRatings = () => {
    const payload = {
      rater_id: raterId,
      session_id: sessionId,
      timestamp: new Date().toISOString(),
      blinded_order: order,
      ratings,
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `rq1_ratings_${raterId || "anon"}_${sessionId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const allRated = MODES.every((m) =>
    CRITERIA.every((c) => typeof ratings[m]?.[c] === "number"),
  );

  return (
    <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">RQ1 — Coach rater (blinded)</h2>
        <span className="text-[11px] text-neutral-500">
          payload modes: cv · hrv · imu · fused
        </span>
      </div>
      <p className="mt-1 text-xs text-neutral-400">
        Generates advice from the 4 payload subsets, randomized per
        session. Rate each on 1–5 Likert across four criteria. Export
        when done — the JSON is your dissertation data.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          className="rounded border border-white/10 bg-black/30 px-2 py-1 text-sm"
          placeholder="rater id (e.g. coach_03)"
          value={raterId}
          onChange={(e) => {
            setRaterId(e.target.value);
            localStorage.setItem("rq1:rater", e.target.value);
          }}
        />
        <button
          onClick={generateAll}
          disabled={generating}
          className="rounded-xl bg-amber-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-amber-400 disabled:bg-neutral-700"
        >
          {generating ? "Generating…" : "Generate 4 variants"}
        </button>
        <button
          onClick={exportRatings}
          disabled={!allRated}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm hover:bg-white/[0.06] disabled:opacity-40"
        >
          Export ratings
        </button>
        <button
          onClick={() => setRevealed((v) => !v)}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/[0.06]"
        >
          {revealed ? "Hide labels" : "Reveal labels"}
        </button>
      </div>

      {err && <p className="mt-2 text-xs text-red-300">{err}</p>}

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
        {order.map((mode, idx) => {
          const v = variants[mode];
          const letter = String.fromCharCode(65 + idx);
          return (
            <div
              key={mode}
              className="rounded-xl border border-white/5 bg-black/30 p-3"
            >
              <div className="flex items-baseline justify-between">
                <div className="text-sm font-semibold">
                  Variant {letter}
                  {revealed && (
                    <span className="ml-2 text-[10px] uppercase tracking-wide text-amber-300">
                      [{mode}]
                    </span>
                  )}
                </div>
              </div>
              {v ? (
                <>
                  <p className="mt-2 text-sm text-neutral-200">{v.summary}</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-neutral-400">
                    {v.action_items.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </>
              ) : (
                <p className="mt-2 text-xs text-neutral-500">
                  not generated yet
                </p>
              )}
              <div className="mt-3 grid grid-cols-2 gap-2">
                {CRITERIA.map((c) => (
                  <LikertRow
                    key={c}
                    label={c}
                    value={ratings[mode]?.[c]}
                    onChange={(n) => setScore(mode, c, n)}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function LikertRow({
  label,
  value,
  onChange,
}: {
  label: string;
  value?: number;
  onChange: (n: number) => void;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className="mt-1 flex gap-1">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            onClick={() => onChange(n)}
            className={`h-7 w-7 rounded text-xs ${
              value === n
                ? "bg-amber-500 text-black"
                : "border border-white/10 text-neutral-300 hover:bg-white/5"
            }`}
          >
            {n}
          </button>
        ))}
      </div>
    </div>
  );
}

function mulberry32(seed: number) {
  return function () {
    let t = (seed += 0x6d2b79f5);
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

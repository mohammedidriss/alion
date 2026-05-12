"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  api,
  type FighterObservationResponse,
  type Session,
} from "@/lib/api";

export default function ObservationsTab({
  params,
}: {
  params: { id: string };
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [aiData, setAiData] = useState<FighterObservationResponse | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiErr, setAiErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .listSessions(params.id)
      .then(setSessions)
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  const annotated = sessions
    .filter((s) => s.notes && s.notes.trim().length > 0)
    .sort((a, b) => b.started_at.localeCompare(a.started_at));

  const completed = sessions.filter((s) => s.status === "completed");

  const generateAI = async () => {
    setAiLoading(true);
    setAiErr(null);
    try {
      const result = await api.generateObservations(params.id);
      setAiData(result);
    } catch (e) {
      setAiErr(String(e));
    } finally {
      setAiLoading(false);
    }
  };

  if (err)
    return <p className="text-sm text-red-400">{err}</p>;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Observations</h1>
        <p className="text-sm text-neutral-400">
          AI-powered training analysis and coach notes from the last 3 months.
        </p>
      </header>

      {/* Headline strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            Sessions (3 mo)
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">
            {completed.length}
          </div>
        </div>
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            Coach notes
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums">
            {annotated.length}
          </div>
        </div>
        <div className="rounded-2xl border border-white/5 bg-white/[0.02] p-3">
          <div className="text-[10px] uppercase tracking-wide text-neutral-500">
            Latest session
          </div>
          <div className="mt-1 text-sm font-semibold">
            {completed[0]
              ? new Date(completed[0].started_at).toLocaleDateString()
              : "—"}
          </div>
        </div>
        <div className="rounded-2xl border border-violet-500/30 bg-violet-500/5 p-3">
          <div className="text-[10px] uppercase tracking-wide text-violet-300/70">
            AI status
          </div>
          <div className="mt-1 text-sm font-semibold text-violet-200">
            {aiData ? "Generated" : aiLoading ? "Analyzing..." : "Ready"}
          </div>
        </div>
      </div>

      {/* ── Part 1: AI Observations ── */}
      <section className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-violet-200">
              AI Training Analysis
            </h2>
            <p className="mt-0.5 text-xs text-neutral-400">
              LLM-generated insights from {completed.length} sessions over the
              last 3 months. Analyzes velocity trends, volume, consistency, and
              recovery.
            </p>
          </div>
          <button
            onClick={generateAI}
            disabled={aiLoading || completed.length < 2}
            className="shrink-0 rounded-xl bg-violet-500 px-4 py-2 text-sm font-semibold text-white shadow-lg shadow-violet-900/30 hover:bg-violet-400 disabled:opacity-50"
          >
            {aiLoading ? "Analyzing..." : aiData ? "Regenerate" : "Generate"}
          </button>
        </div>

        {completed.length < 2 && !aiData && (
          <p className="text-sm text-neutral-400">
            Need at least 2 completed sessions to generate AI analysis.
          </p>
        )}

        {aiErr && <p className="text-sm text-red-300">{aiErr}</p>}

        {aiLoading && !aiData && (
          <div className="flex items-center gap-2 text-sm text-violet-300/80">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-violet-300/30 border-t-violet-300" />
            Analyzing {completed.length} sessions...
          </div>
        )}

        {aiData && (
          <div className="space-y-4">
            {/* Summary */}
            <div className="rounded-lg border border-violet-500/20 bg-violet-500/10 p-4">
              <p className="text-sm text-neutral-100 leading-relaxed">
                {aiData.summary}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
              {/* Observations */}
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-violet-200">
                  Observations
                </h3>
                <ul className="space-y-1.5">
                  {aiData.observations.map((o, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-lg border border-white/5 bg-black/30 p-2.5 text-xs text-neutral-200"
                    >
                      <span className="mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-violet-500/20 text-[10px] font-bold text-violet-300">
                        {i + 1}
                      </span>
                      <span>{o}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Strengths & Weaknesses */}
              <div className="space-y-4">
                {aiData.strengths.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold text-emerald-300">
                      Strengths
                    </h3>
                    <ul className="space-y-1.5">
                      {aiData.strengths.map((s, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-2.5 text-xs text-neutral-200"
                        >
                          <span className="mt-0.5 text-emerald-400">+</span>
                          <span>{s}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {aiData.weaknesses.length > 0 && (
                  <div className="space-y-2">
                    <h3 className="text-sm font-semibold text-amber-300">
                      Areas to Improve
                    </h3>
                    <ul className="space-y-1.5">
                      {aiData.weaknesses.map((w, i) => (
                        <li
                          key={i}
                          className="flex items-start gap-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-xs text-neutral-200"
                        >
                          <span className="mt-0.5 text-amber-400">!</span>
                          <span>{w}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>

            {/* Training Plan */}
            {aiData.training_plan.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-violet-200">
                  Recommended Training Plan
                </h3>
                <ul className="space-y-1.5">
                  {aiData.training_plan.map((t, i) => (
                    <li
                      key={i}
                      className="flex items-start gap-2 rounded-lg border border-violet-500/15 bg-violet-500/5 p-3 text-sm text-neutral-200"
                    >
                      <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-violet-500/25 text-xs font-bold text-violet-300">
                        {i + 1}
                      </span>
                      <span>{t}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </section>

      {/* ── Part 2: Coach Observations ── */}
      <section className="rounded-lg border border-neutral-800 p-5 space-y-4">
        <div>
          <h2 className="text-lg font-semibold">Coach Observations</h2>
          <p className="mt-0.5 text-xs text-neutral-400">
            Free-form notes entered on each session&apos;s detail page.
            Chronological log of coach feedback.
          </p>
        </div>
        {annotated.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No coach notes yet. Open any session and add notes — they&apos;ll
            appear here as a chronological log.
          </p>
        ) : (
          <ul className="space-y-3">
            {annotated.map((s) => (
              <li
                key={s.id}
                className="rounded-lg border border-white/5 bg-black/30 p-4"
              >
                <div className="flex items-center justify-between text-xs text-neutral-500">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-[10px] font-medium">
                      {new Date(s.started_at).toLocaleDateString()}
                    </span>
                    <span>
                      {s.frame_count} frames · {s.duration_ms > 0
                        ? `${(s.duration_ms / 1000).toFixed(0)}s`
                        : "—"}
                    </span>
                  </div>
                  <Link
                    href={`/sessions/${s.id}`}
                    className="text-emerald-400 hover:underline"
                  >
                    open session
                  </Link>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-neutral-100 leading-relaxed">
                  {s.notes}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type Session } from "@/lib/api";

export default function ObservationsTab({
  params,
}: {
  params: { id: string };
}) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .listSessions(params.id)
      .then(setSessions)
      .catch((e) => setErr(String(e)));
  }, [params.id]);

  const annotated = sessions
    .filter((s) => s.notes && s.notes.trim().length > 0)
    .sort((a, b) => b.started_at.localeCompare(a.started_at));

  if (err)
    return <p className="text-sm text-red-400">{err}</p>;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Observations</h1>
        <p className="text-sm text-neutral-400">
          Coach notes per session and (eventually) LLM-generated insights.
        </p>
      </header>

      <section>
        <h2 className="text-base font-semibold">Coach notes</h2>
        <p className="mt-1 text-xs text-neutral-500">
          Free-form annotations entered on each session&apos;s detail page.
        </p>
        {annotated.length === 0 ? (
          <p className="mt-4 text-sm text-neutral-500">
            No coach notes yet. Open any session and add notes — they&apos;ll
            appear here as a chronological log.
          </p>
        ) : (
          <ul className="mt-4 space-y-3">
            {annotated.map((s) => (
              <li key={s.id} className="card">
                <div className="flex items-center justify-between text-xs text-neutral-500">
                  <span>{new Date(s.started_at).toLocaleString()}</span>
                  <Link
                    href={`/sessions/${s.id}`}
                    className="text-emerald-400 hover:underline"
                  >
                    open session →
                  </Link>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm text-neutral-100">
                  {s.notes}
                </p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold">AI recommendations</h2>
          <span className="pill bg-violet-500/15 text-violet-300">coming soon</span>
        </div>
        <p className="mt-1 text-xs text-neutral-500">
          Where LLM-generated coaching observations will land. The model will
          read this fighter&apos;s session metrics, baselines, and notes to
          suggest training focus points and flag changes worth attention.
        </p>
        <div className="mt-3 rounded-2xl border border-dashed border-violet-500/20 bg-violet-500/5 p-4 text-sm text-neutral-400">
          <p className="font-medium text-violet-200">Why this is empty today</p>
          <p className="mt-2">
            Generating real recommendations needs (a) enough longitudinal
            data per fighter to be useful — typically 10+ completed sessions
            with HRV baselines — and (b) a defensible prompt structure that
            doesn&apos;t hallucinate. We&apos;ll wire this up in a later
            phase rather than ship fabricated text.
          </p>
          <p className="mt-3 text-xs text-neutral-500">
            Planned input: per-fighter rolling stats + last-N session
            metrics + HRV trend + notes corpus. Planned output: 3–5 bulleted
            observations with explicit grounding (&ldquo;peak velocity dropped
            8% over the last 3 sessions while RMSSD declined 12 ms — flag for
            recovery&rdquo;).
          </p>
        </div>
      </section>
    </div>
  );
}

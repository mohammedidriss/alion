"use client";

/**
 * Compare models on a recorded session (ADR-049): each chosen model writes the rest
 * cards for every round — the same facts, prompt and verifier as the rest minute —
 * one request at a time, so the timings aren't shared. Each model is woken first
 * (not timed: the first request after a pause also loads it). Nothing is shown to
 * a coach or saved as advice.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { api, type LlmSetup, type LlmTrial, type Session } from "@/lib/api";

const LIMIT_S = 12; // the rest minute waits this long for the model's cards
const MAX_MODELS = 4;
const MAX_ROUNDS = 12;

type Pick = { choice: "local" | "remote"; label: string; model: string };
type Row = { pick: Pick; round: number; trial?: LlmTrial; error?: string };

const keyOf = (p: Pick) => `${p.choice}|${p.model}`;

function errText(e: unknown): string {
  const m = String(e instanceof Error ? e.message : e).match(/^\d{3} (.*)$/s);
  if (m) {
    try {
      const d = JSON.parse(m[1])?.detail;
      if (typeof d === "string") return d;
    } catch {
      /* fall through */
    }
  }
  return String(e instanceof Error ? e.message : e);
}

function summary(rows: Row[]) {
  const done = rows.filter((r) => r.trial?.answered);
  const secs = done.map((r) => r.trial!.seconds);
  const gates: Record<string, number> = {};
  for (const r of rows) {
    for (const v of r.trial?.verdicts ?? []) {
      if (!v.ok && v.gate) {
        const g = v.gate.split(":")[0];
        gates[g] = (gates[g] ?? 0) + 1;
      }
    }
  }
  const topGate = Object.entries(gates).sort((a, b) => b[1] - a[1])[0];
  return {
    rounds: rows.length,
    answered: done.length,
    avg: secs.length ? secs.reduce((a, b) => a + b, 0) / secs.length : null,
    slowest: secs.length ? Math.max(...secs) : null,
    inTime: rows.filter((r) => r.trial?.in_time).length,
    written: rows.reduce((a, r) => a + (r.trial?.written ?? 0), 0),
    passed: rows.reduce((a, r) => a + (r.trial?.passed ?? 0), 0),
    topGate: topGate ? `${topGate[0]} (${topGate[1]})` : null,
    errors: rows.filter((r) => r.error).length,
  };
}

export function ModelCompare({ setups }: { setups: LlmSetup[] }) {
  const choices: Pick[] = useMemo(
    () =>
      setups.flatMap((s) =>
        s.on_own_network ? s.models.map((m) => ({ choice: s.name, label: s.label, model: m })) : [],
      ),
    [setups],
  );
  const [selected, setSelected] = useState<string[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [sessionId, setSessionId] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [step, setStep] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const stop = useRef(false);

  useEffect(() => {
    api
      .listSessions(undefined, { recorded: true })
      .then((all) =>
        setSessions(
          all
            .filter((s) => s.status === "completed" && (s.round_count ?? 0) > 0)
            .sort((a, b) => b.started_at.localeCompare(a.started_at)),
        ),
      )
      .catch((e) => setErr(errText(e)));
    api
      .listFighters()
      .then((fs) => setNames(Object.fromEntries(fs.map((f) => [f.id, f.name]))))
      .catch(() => {});
  }, []);

  const session = sessions.find((s) => s.id === sessionId);
  const picks = choices.filter((c) => selected.includes(keyOf(c)));

  const run = async () => {
    if (!session || picks.length === 0) return;
    stop.current = false;
    setErr(null);
    const rounds = Math.min(session.round_count ?? 0, MAX_ROUNDS);
    const plan: Row[] = picks.flatMap((pick) =>
      Array.from({ length: rounds }, (_, i) => ({ pick, round: i + 1 })),
    );
    setRows(plan);
    for (const pick of picks) {
      if (stop.current) break;
      setStep(`Waking ${pick.model} on ${pick.label} (not timed)…`);
      await api.testLlm(pick.choice, pick.model).catch(() => undefined);
      for (let round = 1; round <= rounds; round++) {
        if (stop.current) break;
        setStep(`${pick.model} on ${pick.label} — round ${round} of ${rounds}…`);
        let row: Row;
        try {
          const trial = await api.llmTrial({
            choice: pick.choice,
            model: pick.model,
            session_id: session.id,
            after_round: round,
          });
          row = { pick, round, trial };
        } catch (e) {
          row = { pick, round, error: errText(e) };
        }
        setRows((rs) => rs.map((r) => (keyOf(r.pick) === keyOf(pick) && r.round === round ? row : r)));
      }
    }
    setStep(null);
  };

  const byModel = picks.length
    ? picks.map((p) => ({ pick: p, rows: rows.filter((r) => keyOf(r.pick) === keyOf(p)) }))
    : [];
  const roundsRun = Array.from(new Set(rows.map((r) => r.round))).sort((a, b) => a - b);

  return (
    <section className="card space-y-4">
      <header>
        <h2 className="text-lg font-semibold">Compare models</h2>
        <p className="mt-1 text-sm text-neutral-400">
          Each model writes the rest cards for every round of a recorded session — the same facts,
          prompt and checks as the rest minute, one request at a time. A card counts only if it passes
          every check; the rest minute waits {LIMIT_S} s for them. Nothing is shown to a coach or saved
          as advice.
        </p>
      </header>

      <div className="space-y-2">
        <div className="text-xs font-medium text-neutral-400">Models (up to {MAX_MODELS})</div>
        <div className="flex flex-wrap gap-2">
          {choices.map((c) => {
            const k = keyOf(c);
            const on = selected.includes(k);
            return (
              <label
                key={k}
                className={`flex cursor-pointer items-center gap-2 rounded-xl border px-3 py-1.5 text-xs ${
                  on ? "border-emerald-500/60 bg-emerald-950/30" : "border-white/10"
                }`}
              >
                <input
                  type="checkbox"
                  checked={on}
                  disabled={step !== null || (!on && selected.length >= MAX_MODELS)}
                  onChange={(e) =>
                    setSelected((s) => (e.target.checked ? [...s, k] : s.filter((x) => x !== k)))
                  }
                />
                <span className="font-mono">{c.model}</span>
                <span className="text-neutral-500">{c.label}</span>
              </label>
            );
          })}
        </div>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium text-neutral-400">Session</div>
        <select
          value={sessionId}
          disabled={step !== null}
          onChange={(e) => setSessionId(e.target.value)}
          className="w-full rounded-xl border border-white/10 bg-neutral-900 px-3 py-2 text-sm text-neutral-200"
        >
          <option value="">— a recorded session with rounds —</option>
          {sessions.map((s) => (
            <option key={s.id} value={s.id}>
              {[names[s.fighter_id], new Date(s.started_at).toLocaleString(), `${s.round_count} rounds`]
                .filter(Boolean)
                .join(" · ")}
            </option>
          ))}
        </select>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        {step === null ? (
          <button
            onClick={run}
            disabled={!session || picks.length === 0}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
          >
            Compare
          </button>
        ) : (
          <button
            onClick={() => (stop.current = true)}
            className="rounded-xl border border-white/10 px-4 py-2 text-sm text-neutral-200 hover:bg-white/5"
          >
            Stop
          </button>
        )}
        {step && <span className="text-sm text-neutral-400">{step}</span>}
      </div>
      {err && <p className="text-sm text-red-300">{err}</p>}

      {byModel.length > 0 && rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="text-left text-xs text-neutral-500">
              <tr>
                <th className="py-2 pr-3 font-medium">Model</th>
                <th className="py-2 pr-3 font-medium">Average</th>
                <th className="py-2 pr-3 font-medium">Slowest</th>
                <th className="py-2 pr-3 font-medium">In time</th>
                <th className="py-2 pr-3 font-medium">Cards passed</th>
                <th className="py-2 font-medium">Failed most on</th>
              </tr>
            </thead>
            <tbody>
              {byModel.map(({ pick, rows: rs }) => {
                const m = summary(rs);
                return (
                  <tr key={keyOf(pick)} className="border-t border-white/5">
                    <td className="py-2 pr-3">
                      <div className="font-mono text-neutral-200">{pick.model}</div>
                      <div className="text-xs text-neutral-500">{pick.label}</div>
                    </td>
                    <td className="py-2 pr-3">{m.avg !== null ? `${m.avg.toFixed(1)} s` : "—"}</td>
                    <td className="py-2 pr-3">{m.slowest !== null ? `${m.slowest.toFixed(1)} s` : "—"}</td>
                    <td className="py-2 pr-3">
                      {m.inTime} / {m.rounds} rounds
                    </td>
                    <td className="py-2 pr-3">
                      {m.passed} / {m.written} written
                      <div className="text-xs text-neutral-500">of {3 * m.rounds} slots</div>
                    </td>
                    <td className="py-2 text-xs text-neutral-400">
                      {m.topGate ?? "—"}
                      {m.errors > 0 && <div className="text-red-300">{m.errors} round(s) failed</div>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {roundsRun.map((round) => (
        <details key={round} className="rounded-xl border border-white/5 p-3">
          <summary className="cursor-pointer text-sm text-neutral-300">After round {round}</summary>
          <div className="mt-3 grid gap-3" style={{ gridTemplateColumns: `repeat(${byModel.length}, minmax(0, 1fr))` }}>
            {byModel.map(({ pick, rows: rs }) => {
              const r = rs.find((x) => x.round === round);
              return (
                <div key={keyOf(pick)} className="min-w-0 space-y-2">
                  <div className="font-mono text-xs text-neutral-400">
                    {pick.model}
                    {r?.trial && ` · ${r.trial.seconds} s`}
                  </div>
                  {!r?.trial && !r?.error && <div className="text-xs text-neutral-500">waiting…</div>}
                  {r?.error && <div className="text-xs text-red-300">{r.error}</div>}
                  {r?.trial && !r.trial.answered && (
                    <div className="text-xs text-amber-300">No usable answer — the templates stay.</div>
                  )}
                  {r?.trial?.cards.map((c) => (
                    <div key={c.slot} className="rounded-lg bg-white/[0.03] p-2">
                      <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-neutral-500">
                        <span>{c.slot}</span>
                        <span className={c.source === "model" ? "text-emerald-300" : ""}>
                          {c.source === "model" ? "model" : "template"}
                        </span>
                      </div>
                      <div className="text-sm text-neutral-200">{c.headline}</div>
                      {c.context && <div className="text-xs text-neutral-400">{c.context}</div>}
                    </div>
                  ))}
                  {r?.trial?.verdicts
                    .filter((v) => !v.ok)
                    .map((v, i) => (
                      <div key={i} className="text-[11px] text-amber-300/80">
                        {v.slot ?? "card"} dropped — {v.gate}
                      </div>
                    ))}
                  {r?.trial && r.trial.blocked_terms.length > 0 && (
                    <div className="text-[11px] text-red-300">
                      Withheld: blocked term ({r.trial.blocked_terms.join(", ")})
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </details>
      ))}
    </section>
  );
}

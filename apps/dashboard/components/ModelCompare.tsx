"use client";

/**
 * Comparing language models on recorded sessions (ADR-049, ADR-058). A comparison
 * runs on the server — every chosen model phrases the rest cards of every round of
 * the chosen sessions, as many times as asked, one request at a time — and is
 * saved: it keeps going if the page is left, and stays in the history.
 *
 * Each model has a blind code (A, B, …): until "Reveal names", the results and the
 * cards show the code only, so the cards are rated on their merit — how useful
 * they'd be to a coach in the rest minute. Then: download the CSV, or use the model.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type LlmComparison,
  type LlmComparisonTrial,
  type LlmSetup,
  type Session,
} from "@/lib/api";

const MAX_MODELS = 4;
const MAX_SESSIONS = 5;
const LIMIT_S = 12; // the rest minute waits this long for the model's cards

type Pick = { choice: "local" | "remote"; model: string; label: string };
const keyOf = (p: { choice: string; model: string }) => `${p.choice}|${p.model}`;

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

/** A stable order of the codes for one round: the same each time it's drawn, not A-B-C. */
function shuffledCodes(codes: string[], key: string): string[] {
  const h = (s: string) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
  return [...codes].sort((a, b) => h(key + a) - h(key + b));
}

export function ModelCompare({ setups, onChosen }: { setups: LlmSetup[]; onChosen?: () => void }) {
  const [history, setHistory] = useState<LlmComparison[]>([]);
  const [current, setCurrent] = useState<LlmComparison | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadHistory = useCallback(async () => {
    try {
      const h = await api.llmComparisons();
      setHistory(h);
      return h;
    } catch (e) {
      setErr(errText(e));
      return [];
    }
  }, []);

  const open = useCallback(async (id: string) => {
    try {
      setCurrent(await api.llmComparison(id));
    } catch (e) {
      setErr(errText(e));
    }
  }, []);

  useEffect(() => {
    void loadHistory().then((h) => h[0] && open(h[0].id));
  }, [loadHistory, open]);

  // Follow a running comparison.
  useEffect(() => {
    if (current?.status !== "running") return;
    const t = setInterval(() => void open(current.id).then(() => loadHistory()), 3000);
    return () => clearInterval(t);
  }, [current?.status, current?.id, open, loadHistory]);

  const running = history.some((c) => c.status === "running");
  return (
    <section className="card space-y-5">
      <header>
        <h2 className="text-lg font-semibold">Compare models</h2>
        <p className="mt-1 text-sm text-neutral-400">
          Each model writes the rest cards for every round of the sessions you pick — the same facts, prompt and checks
          as the rest minute — as many times as you ask, one request at a time. It runs on the server and is saved: you
          can leave the page. Models show as A, B, … until you reveal their names, so you can rate the cards blind.
          Nothing is shown to a coach or saved as advice.
        </p>
      </header>
      {err && <p className="text-sm text-red-300">{err}</p>}
      <NewComparison
        setups={setups}
        busy={running}
        onStarted={async (c) => {
          setErr(null);
          setCurrent(c);
          await loadHistory();
        }}
        onError={setErr}
      />
      {history.length > 0 && (
        <div className="space-y-1">
          <div className="text-xs font-medium text-neutral-400">Saved comparisons</div>
          <div className="flex flex-wrap gap-2">
            {history.map((c) => (
              <button
                key={c.id}
                onClick={() => void open(c.id)}
                className={`rounded-xl border px-3 py-1.5 text-left text-xs ${
                  current?.id === c.id ? "border-emerald-500/60 bg-emerald-950/30" : "border-white/10 hover:bg-white/5"
                }`}
              >
                <div className="text-neutral-200">{new Date(c.created_at).toLocaleString()}</div>
                <div className="text-neutral-500">
                  {c.models.length} models · {c.sessions.length} session{c.sessions.length === 1 ? "" : "s"} ·{" "}
                  {c.status === "running" ? `${c.done}/${c.total}` : c.status}
                  {c.revealed ? " · revealed" : ""}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
      {current && (
        <ComparisonView
          c={current}
          onChanged={(c) => {
            setCurrent(c);
            void loadHistory();
          }}
          onChosen={onChosen}
          onError={setErr}
        />
      )}
    </section>
  );
}

function NewComparison({
  setups,
  busy,
  onStarted,
  onError,
}: {
  setups: LlmSetup[];
  busy: boolean;
  onStarted: (c: LlmComparison) => void;
  onError: (e: string) => void;
}) {
  const choices: Pick[] = useMemo(
    () => setups.flatMap((s) => (s.on_own_network ? s.models.map((m) => ({ choice: s.name, model: m, label: s.label })) : [])),
    [setups],
  );
  const [models, setModels] = useState<string[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [names, setNames] = useState<Record<string, string>>({});
  const [picked, setPicked] = useState<string[]>([]);
  const [repeats, setRepeats] = useState(1);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api
      .listSessions(undefined, { recorded: true })
      .then((all) =>
        setSessions(
          all
            .filter((s) => s.status === "completed" && (s.round_count ?? 0) > 0)
            .sort((a, b) => b.started_at.localeCompare(a.started_at))
            .slice(0, 40),
        ),
      )
      .catch(() => setSessions([]));
    api
      .listFighters()
      .then((fs) => setNames(Object.fromEntries(fs.map((f) => [f.id, f.name]))))
      .catch(() => {});
  }, []);

  const rounds = sessions.filter((s) => picked.includes(s.id)).reduce((a, s) => a + Math.min(s.round_count ?? 0, 12), 0);
  const requests = models.length * repeats * rounds;

  const start = async () => {
    setStarting(true);
    try {
      const chosen = choices.filter((c) => models.includes(keyOf(c)));
      onStarted(
        await api.startLlmComparison({
          models: chosen.map((c) => ({ choice: c.choice, model: c.model })),
          session_ids: picked,
          repeats,
        }),
      );
    } catch (e) {
      onError(errText(e));
    } finally {
      setStarting(false);
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-white/10 p-3">
      <div className="text-sm font-medium text-neutral-200">New comparison</div>
      <div className="space-y-1">
        <div className="text-xs text-neutral-400">Models (up to {MAX_MODELS})</div>
        <div className="flex flex-wrap gap-2">
          {choices.map((c) => {
            const k = keyOf(c);
            const on = models.includes(k);
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
                  disabled={!on && models.length >= MAX_MODELS}
                  onChange={(e) => setModels((m) => (e.target.checked ? [...m, k] : m.filter((x) => x !== k)))}
                />
                <span className="font-mono">{c.model}</span>
                <span className="text-neutral-500">{c.label}</span>
              </label>
            );
          })}
        </div>
      </div>
      <div className="space-y-1">
        <div className="text-xs text-neutral-400">Sessions (up to {MAX_SESSIONS}) — more sessions, a fairer comparison</div>
        <div className="max-h-44 space-y-0.5 overflow-y-auto rounded-xl border border-white/5 p-2">
          {sessions.map((s) => {
            const on = picked.includes(s.id);
            return (
              <label key={s.id} className="flex cursor-pointer items-center gap-2 text-xs text-neutral-300">
                <input
                  type="checkbox"
                  checked={on}
                  disabled={!on && picked.length >= MAX_SESSIONS}
                  onChange={(e) => setPicked((p) => (e.target.checked ? [...p, s.id] : p.filter((x) => x !== s.id)))}
                />
                {[names[s.fighter_id], new Date(s.started_at).toLocaleString(), `${s.round_count} rounds`].filter(Boolean).join(" · ")}
              </label>
            );
          })}
          {sessions.length === 0 && <div className="text-xs text-neutral-500">No recorded sessions with rounds yet.</div>}
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2 text-xs text-neutral-400">
          Runs of each round
          <select value={repeats} onChange={(e) => setRepeats(Number(e.target.value))} className="rounded-lg border border-white/10 bg-neutral-900 px-2 py-1 text-sm text-neutral-200">
            {[1, 2, 3].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <button
          onClick={() => void start()}
          disabled={busy || starting || models.length === 0 || picked.length === 0}
          title={busy ? "A comparison is running — stop it or wait" : undefined}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          {starting ? "Starting…" : "Start"}
        </button>
        {requests > 0 && (
          <span className="text-xs text-neutral-500">
            {requests} requests — roughly {Math.max(1, Math.round((requests * 8) / 60))}–{Math.max(1, Math.round((requests * 25) / 60))} min
          </span>
        )}
      </div>
    </div>
  );
}

function ComparisonView({
  c,
  onChanged,
  onChosen,
  onError,
}: {
  c: LlmComparison;
  onChanged: (c: LlmComparison) => void;
  onChosen?: () => void;
  onError: (e: string) => void;
}) {
  const act = async (fn: () => Promise<LlmComparison | unknown>) => {
    try {
      await fn();
      onChanged(await api.llmComparison(c.id));
    } catch (e) {
      onError(errText(e));
    }
  };
  const label = (code: string) => {
    const m = c.models.find((x) => x.code === code);
    return c.revealed && m?.model ? `${code} · ${m.model}` : `Model ${code}`;
  };
  const pct = c.total ? Math.round((100 * c.done) / c.total) : 0;

  return (
    <div className="space-y-4">
      {c.status === "running" && (
        <div className="space-y-1">
          <div className="h-2 overflow-hidden rounded-full bg-white/5">
            <div className="h-full bg-emerald-500" style={{ width: `${pct}%` }} />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-neutral-400">
            <span>
              {c.done} of {c.total} · {c.step}
            </span>
            <button onClick={() => void act(() => api.stopLlmComparison(c.id))} className="rounded-lg border border-white/10 px-2.5 py-1 text-neutral-300 hover:bg-white/5">
              Stop
            </button>
          </div>
        </div>
      )}
      {c.status !== "running" && (
        <p className="text-xs text-neutral-500">
          {c.status === "done" ? "Finished" : c.status === "stopped" ? "Stopped" : "Failed"}
          {c.finished_at && ` ${new Date(c.finished_at).toLocaleString()}`} · {c.done} of {c.total} requests · {c.repeats} run
          {c.repeats === 1 ? "" : "s"} of each round
          {c.status === "failed" && c.step && ` · ${c.step}`}
        </p>
      )}

      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead className="text-left text-xs text-neutral-500">
            <tr>
              <th className="py-2 pr-3 font-medium">Model</th>
              <th className="py-2 pr-3 font-medium">Median · slowest</th>
              <th className="py-2 pr-3 font-medium">In time ({LIMIT_S} s)</th>
              <th className="py-2 pr-3 font-medium">Cards passed</th>
              <th className="py-2 pr-3 font-medium" title="Of rounds run more than once, the share that passed as many cards every time">
                Consistent
              </th>
              <th className="py-2 pr-3 font-medium">Your rating</th>
              <th className="py-2 font-medium">Failed most on</th>
            </tr>
          </thead>
          <tbody>
            {c.models.map((m) => (
              <tr key={m.code} className="border-t border-white/5">
                <td className="py-2 pr-3">
                  <div className="font-mono text-neutral-100">{label(m.code)}</div>
                  {c.revealed && m.label && <div className="text-xs text-neutral-500">{m.label}</div>}
                  {c.revealed && m.choice && m.model && (
                    m.in_use ? (
                      <span className="mt-1 inline-block rounded-full bg-emerald-900/60 px-2 py-0.5 text-[10px] text-emerald-200">in use</span>
                    ) : (
                      <button
                        onClick={() =>
                          void act(async () => {
                            await api.chooseLlm(m.choice as "local" | "remote", m.model);
                            onChosen?.();
                          })
                        }
                        className="mt-1 rounded-lg bg-emerald-500 px-2 py-0.5 text-[11px] font-semibold text-black hover:bg-emerald-400"
                      >
                        Use this one
                      </button>
                    )
                  )}
                </td>
                <td className="py-2 pr-3">
                  {m.median_seconds !== null ? `${m.median_seconds.toFixed(1)} s · ${m.slowest_seconds?.toFixed(1)} s` : "—"}
                </td>
                <td className="py-2 pr-3">
                  {m.in_time} / {m.trials}
                </td>
                <td className="py-2 pr-3">
                  {m.passed} / {m.written} written
                  <div className="text-xs text-neutral-500">of {m.slots} slots</div>
                </td>
                <td className="py-2 pr-3">{m.consistent !== null ? `${Math.round(m.consistent * 100)}%` : "—"}</td>
                <td className="py-2 pr-3">
                  {m.rating !== null ? `${m.rating.toFixed(1)} / 5` : "—"}
                  {m.ratings > 0 && <div className="text-xs text-neutral-500">{m.ratings} rated{m.blind_rating !== null ? `, blind ${m.blind_rating.toFixed(1)}` : ""}</div>}
                </td>
                <td className="py-2 text-xs text-neutral-400">
                  {m.top_gate ?? "—"}
                  {m.errors > 0 && <div className="text-red-300">{m.errors} failed</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex flex-wrap gap-2">
        {!c.revealed && (
          <button
            onClick={() => {
              if (confirm("Reveal which model is which? Ratings you give after this are marked as not blind.")) void act(() => api.revealLlmComparison(c.id));
            }}
            className="rounded-xl border border-white/10 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
          >
            Reveal names
          </button>
        )}
        <button
          onClick={() => void api.downloadLlmComparisonCsv(c.id).catch((e) => onError(errText(e)))}
          className="rounded-xl border border-white/10 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5"
        >
          Download CSV
        </button>
      </div>

      {c.trials && c.trials.length > 0 && <RateCards c={c} label={label} onRated={() => void act(async () => undefined)} onError={onError} />}
    </div>
  );
}

function RateCards({
  c,
  label,
  onRated,
  onError,
}: {
  c: LlmComparison;
  label: (code: string) => string;
  onRated: () => void;
  onError: (e: string) => void;
}) {
  // The first run of every round: each model's cards side by side, in a shuffled order.
  const rounds = useMemo(() => {
    const out = new Map<string, LlmComparisonTrial[]>();
    for (const t of c.trials ?? []) {
      if (t.repeat !== 1) continue;
      const k = `${t.session_id}|${t.after_round}`;
      out.set(k, [...(out.get(k) ?? []), t]);
    }
    return [...out.entries()];
  }, [c.trials]);
  const sessionNo = (id: string) => c.sessions.findIndex((s) => s.id === id) + 1;
  const toRate = (c.trials ?? []).filter((t) => t.repeat === 1 && t.answered);
  const rated = toRate.filter((t) => t.my_score !== null).length;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold text-neutral-200">Rate the cards{c.revealed ? "" : " — blind"}</h3>
        <span className="text-xs text-neutral-500">
          {rated} of {toRate.length} rated · how useful would these be to a coach in the rest minute? (1–5)
        </span>
      </div>
      {rounds.map(([k, trials]) => {
        const [sid, rnd] = k.split("|");
        const order = shuffledCodes(trials.map((t) => t.code), k);
        return (
          <details key={k} className="rounded-xl border border-white/5 p-3">
            <summary className="cursor-pointer text-sm text-neutral-300">
              Session {sessionNo(sid)}, after round {rnd}
              {trials.every((t) => !t.answered || t.my_score !== null) && <span className="ml-2 text-xs text-emerald-300">✓ rated</span>}
            </summary>
            <div className="mt-3 grid gap-3" style={{ gridTemplateColumns: `repeat(${order.length}, minmax(0, 1fr))` }}>
              {order.map((code) => {
                const t = trials.find((x) => x.code === code);
                if (!t) return <div key={code} />;
                return (
                  <div key={code} className="min-w-0 space-y-2">
                    <div className="font-mono text-xs text-neutral-400">
                      {label(code)}
                      {t.seconds !== null && ` · ${t.seconds} s`}
                    </div>
                    {t.detail.error && <div className="text-xs text-red-300">{t.detail.error}</div>}
                    {!t.answered && !t.detail.error && (
                      <div className="text-xs text-amber-300">
                        {t.detail.facts === 0 ? "No facts to phrase this round." : "No usable answer — the templates stay."}
                      </div>
                    )}
                    {(t.detail.cards ?? []).map((card) => (
                      <div key={card.slot} className="rounded-lg bg-white/[0.03] p-2">
                        <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wide text-neutral-500">
                          <span>{card.slot}</span>
                          <span className={card.source === "model" ? "text-emerald-300" : ""}>{card.source === "model" ? "model" : "template"}</span>
                        </div>
                        <div className="text-sm text-neutral-200">{card.headline}</div>
                        {card.context && <div className="text-xs text-neutral-400">{card.context}</div>}
                      </div>
                    ))}
                    {(t.detail.verdicts ?? [])
                      .filter((v) => !v.ok)
                      .map((v, i) => (
                        <div key={i} className="text-[11px] text-amber-300/80">
                          {v.slot ?? "card"} dropped — {v.gate}
                        </div>
                      ))}
                    {t.answered && (
                      <div className="flex gap-1">
                        {[1, 2, 3, 4, 5].map((n) => (
                          <button
                            key={n}
                            onClick={() =>
                              void api
                                .rateLlmTrial(c.id, t.id, n)
                                .then(onRated)
                                .catch((e) => onError(errText(e)))
                            }
                            className={`h-7 w-7 rounded-lg text-xs ${
                              t.my_score !== null && n <= t.my_score ? "bg-amber-400 text-black" : "bg-white/5 text-neutral-400 hover:bg-white/10"
                            }`}
                          >
                            {n}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </details>
        );
      })}
    </div>
  );
}

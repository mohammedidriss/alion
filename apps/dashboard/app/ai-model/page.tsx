"use client";

/**
 * Which AI writes the coach's advice: the local one (this computer) or the remote
 * one (another computer on your network) — switched here, no restart, from the
 * next advice request on (ADR-021). Researchers and admins only.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type LlmSetup, type LlmStatus } from "@/lib/api";

type TestResult = { ok: boolean; seconds: number; reply?: string; error?: string };

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
  return String(e);
}

export default function AiModelPage() {
  const [st, setSt] = useState<LlmStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<string, TestResult>>({});

  const load = useCallback(
    () =>
      api
        .llmStatus()
        .then((s) => {
          setSt(s);
          setErr(null);
        })
        .catch((e) => setErr(errText(e))),
    [],
  );
  useEffect(() => {
    load();
  }, [load]);

  const choose = async (s: LlmSetup) => {
    setBusy(`use-${s.name}`);
    setErr(null);
    try {
      setSt(await api.chooseLlm(s.name));
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const test = async (s: LlmSetup) => {
    setBusy(`test-${s.name}`);
    try {
      const r = await api.testLlm(s.name);
      setTests((t) => ({ ...t, [s.name]: r }));
    } catch (e) {
      setTests((t) => ({ ...t, [s.name]: { ok: false, seconds: 0, error: errText(e) } }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header>
        <h1 className="text-2xl font-semibold">AI model</h1>
        <p className="mt-1 text-sm text-neutral-400">
          Which computer writes the coach&apos;s advice. Switching takes effect on the next advice
          request — no restart. Every piece of advice records which model wrote it.
        </p>
      </header>

      {err && (
        <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>
      )}

      {st && st.setups.length === 0 && (
        <p className="card text-sm text-neutral-300">
          No local or remote AI is set up yet, so advice uses <span className="font-mono">{st.in_use.model}</span>{" "}
          at <span className="font-mono">{st.in_use.url}</span>. Add <span className="font-mono">ALION_LLM_LOCAL_URL</span>{" "}
          and <span className="font-mono">ALION_LLM_REMOTE_URL</span> to <span className="font-mono">.env</span> to switch
          between two.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        {st?.setups.map((s) => {
          const ok = s.reachable && s.model_installed;
          const t = tests[s.name];
          return (
            <section
              key={s.name}
              className={`card space-y-3 ${s.active ? "ring-1 ring-emerald-500/60" : ""}`}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="text-xs uppercase tracking-wide text-neutral-500">
                    {s.name === "local" ? "Local" : "Remote"}
                  </div>
                  <h2 className="text-base font-semibold">{s.label}</h2>
                </div>
                {s.active && (
                  <span className="rounded-full bg-emerald-900/60 px-2.5 py-0.5 text-xs text-emerald-200">In use</span>
                )}
              </div>
              <dl className="space-y-1 text-xs">
                <div className="flex justify-between gap-2">
                  <dt className="text-neutral-500">Model</dt>
                  <dd className="font-mono text-neutral-200">{s.model}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-neutral-500">Address</dt>
                  <dd className="truncate font-mono text-neutral-300">{s.url}</dd>
                </div>
              </dl>
              <p className={`text-sm ${ok ? "text-emerald-300" : "text-amber-300"}`}>
                {!s.on_own_network
                  ? "Not on your own network — refused, so session data stays local."
                  : !s.reachable
                    ? "Not answering — is it switched on, with Ollama running?"
                    : !s.model_installed
                      ? `Answering, but ${s.model} isn't installed there.`
                      : "Ready."}
              </p>
              {t && (
                <p className={`text-xs ${t.ok ? "text-neutral-300" : "text-red-300"}`}>
                  {t.ok
                    ? `Answered in ${t.seconds} s${t.reply ? ` (“${t.reply}”)` : ""}. The first request after a pause also loads the model.`
                    : `Test failed after ${t.seconds} s: ${t.error}`}
                </p>
              )}
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() => test(s)}
                  disabled={busy !== null || !s.on_own_network}
                  className="rounded-xl border border-white/10 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-40"
                >
                  {busy === `test-${s.name}` ? "Testing…" : "Test"}
                </button>
                {!s.active && (
                  <button
                    onClick={() => choose(s)}
                    disabled={busy !== null || !s.on_own_network}
                    title={ok ? undefined : "It isn't ready — advice would fail until it is"}
                    className="rounded-xl bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
                  >
                    {busy === `use-${s.name}` ? "Switching…" : "Use this one"}
                  </button>
                )}
              </div>
            </section>
          );
        })}
      </div>

      <button onClick={load} className="text-xs text-neutral-500 underline hover:text-neutral-300">
        Check again
      </button>
    </div>
  );
}

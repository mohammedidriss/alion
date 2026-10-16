"use client";

/**
 * AI models (ADR-057): every model in one place, for researchers and admins.
 *
 * Punch models — the camera punch counter, and punch types from the cameras and
 * from the wrist sensors: what each does, what it learns from (the research
 * datasets and the training sessions recorded with wrists and cameras, ADR-047),
 * its score on data it never saw, and Train.
 *
 * The coach's language model — which computer writes the advice, the local one or
 * the remote one, and which of the models installed there, switched with no
 * restart (ADR-021, ADR-049); and comparing them on a recorded session's rest cards.
 */

import { useCallback, useEffect, useState } from "react";
import { CameraTypesCard } from "@/components/CameraTypesCard";
import { TrainingCard } from "@/components/TrainingCard";
import { WristCounterCard } from "@/components/WristCounterCard";
import { WristTypesCard } from "@/components/WristTypesCard";
import { api, type DatasetSummary, type LlmSetup, type LlmStatus, type ProtocolBlockSpec } from "@/lib/api";
import { ModelCompare } from "@/components/ModelCompare";
import { useAuth } from "@/lib/auth";

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

type Tab = "punch" | "language";

export default function AiModelsPage() {
  const [tab, setTab] = useState<Tab>("punch");
  const [datasetId, setDatasetId] = useState<string | null>(null);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    if (q.get("tab") === "language") setTab("language");
    setDatasetId(q.get("dataset"));
  }, []);
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header>
        <h1 className="text-2xl font-semibold">AI models</h1>
        <p className="mt-1 text-sm text-neutral-400">
          The models that read the recordings, and the language model that writes the coach&apos;s advice. Each
          punch model learns from your research datasets and from the training sessions recorded with wrists and
          cameras, and is scored on data it never saw.
        </p>
      </header>
      <nav className="flex gap-2">
        {(
          [
            ["punch", "Punch models"],
            ["language", "Coach's language model"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`rounded-full px-4 py-1.5 text-sm ${
              tab === k ? "bg-white/10 text-white" : "bg-white/[0.03] text-neutral-400 hover:bg-white/[0.07]"
            }`}
          >
            {label}
          </button>
        ))}
      </nav>
      {tab === "punch" ? <PunchModels initialDataset={datasetId} /> : <LanguageModel />}
    </div>
  );
}

/** One model's heading: what it does and what it learns from, the same for each. */
function ModelHeading({ title, does, learns }: { title: string; does: string; learns: string }) {
  return (
    <div className="space-y-0.5 px-1">
      <h2 className="text-lg font-semibold">{title}</h2>
      <p className="text-sm text-neutral-400">{does}</p>
      <p className="text-xs text-neutral-500">Learns from: {learns}</p>
    </div>
  );
}

/** Which counter counts the cameras' punches after a recording (ADR-059): the
 *  newest trained one — live, each camera shows its own quick estimate. */
function CounterInUse() {
  type InUse = Awaited<ReturnType<typeof api.punchCounter>>["counter"];
  const [c, setC] = useState<InUse | undefined>(undefined);
  useEffect(() => {
    api
      .punchCounter()
      .then((r) => setC(r.counter))
      .catch(() => setC(undefined));
  }, []);
  if (c === undefined) return null;
  const pct = (v: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  return (
    <p className="px-1 text-xs text-neutral-400">
      {c ? (
        <>
          In use after each recording:{" "}
          <span className="text-neutral-200">
            v{c.version} trained on {c.dataset_name ?? "a dataset"}
          </span>
          {c.created_at && ` (${new Date(c.created_at).toLocaleDateString()})`} — {pct(c.f1)} of
          punches right on its test takes vs {pct(c.f1_detector)} for the hand-written detector.
          The newest trained counter is the one in use.
        </>
      ) : (
        "In use after each recording: the hand-written detector — train a counter to replace it."
      )}
    </p>
  );
}

function PunchModels({ initialDataset }: { initialDataset: string | null }) {
  const [datasets, setDatasets] = useState<DatasetSummary[]>([]);
  const [plan, setPlan] = useState<ProtocolBlockSpec[]>([]);
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => {
    api
      .listDatasets()
      .then((d) => {
        const protocol = d.filter((x) => x.protocol);
        setDatasets(protocol);
        setPicked((cur) => cur ?? (initialDataset && protocol.some((x) => x.id === initialDataset) ? initialDataset : protocol[0]?.id ?? null));
      })
      .catch(() => setDatasets([]));
    api.protocolPlan().then(setPlan).catch(() => setPlan([]));
  }, [initialDataset]);
  const ds = datasets.find((d) => d.id === picked);

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <ModelHeading
          title="Punch counter — cameras"
          does="Counts punches, and which hand threw them, from the cameras' pose."
          learns="a protocol dataset's exported takes, the other exported datasets' takes (the wrist sensors give each punch's time) and every training session recorded with wrists and cameras; scored on the dataset's test takes, next to today's counter."
        />
        <CounterInUse />
        {datasets.length > 1 && (
          <select
            value={picked ?? ""}
            onChange={(e) => setPicked(e.target.value)}
            className="rounded-xl border border-white/10 bg-neutral-900 px-3 py-2 text-sm text-neutral-200"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} — {d.completed_takes} takes
              </option>
            ))}
          </select>
        )}
        {ds && plan.length > 0 ? (
          <TrainingCard datasetId={ds.id} plan={plan} canTrain={ds.completed_takes > 0} />
        ) : (
          <p className="card text-sm text-neutral-500">Record a protocol dataset first — the counter is scored on its test takes.</p>
        )}
      </section>
      <section className="space-y-3">
        <ModelHeading
          title="Punch counter — wrist sensors"
          does="Counts each wrist's punches without knowing their type — live while recording, and in every session's numbers and cross-check. It finds every burst a sensitive setting can, then keeps the ones that are punches: a gentle hook stays, an uppercut's return to guard and a still hand's shake go."
          learns="every dataset's labelled protocol blocks — the single-punch blocks (labelled with each type's own settings), the no-punch block and whole combos; scored on takes it never trained on, next to the fixed settings it replaces."
        />
        <WristCounterCard />
      </section>
      <section className="space-y-3">
        <ModelHeading
          title="Punch types — cameras"
          does="Names each punch — straight, hook or uppercut; jab or cross by stance — from the arm's 3D motion after a session. Two or more cameras that saw it decide together; with one camera the wrist sensor joins in; with none the wrist names it alone."
          learns="every dataset's labelled takes, and the recorded training sessions someone labelled with punch types."
        />
        <CameraTypesCard />
      </section>
      <section className="space-y-3">
        <ModelHeading
          title="Punch types — wrist sensors"
          does="Names each punch straight, hook or uppercut from the wrists alone (jab or cross from the hand and the stance) — on every session's per-round breakdown."
          learns="every dataset's labelled takes, and the recorded training sessions someone labelled with punch types."
        />
        <WristTypesCard />
      </section>
    </div>
  );
}

function LanguageModel() {
  const { user } = useAuth();
  const [st, setSt] = useState<LlmStatus | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tests, setTests] = useState<Record<string, TestResult>>({});
  const [picked, setPicked] = useState<Record<string, string>>({}); // setup → model, not yet in use

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

  const choose = async (s: LlmSetup, model?: string) => {
    setBusy(`use-${s.name}`);
    setErr(null);
    try {
      setSt(await api.chooseLlm(s.name, model ?? picked[s.name]));
      setPicked((p) => {
        const { [s.name]: _, ...rest } = p;
        return rest;
      });
    } catch (e) {
      setErr(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const test = async (s: LlmSetup) => {
    setBusy(`test-${s.name}`);
    try {
      const r = await api.testLlm(s.name, picked[s.name] ?? s.model);
      setTests((t) => ({ ...t, [s.name]: r }));
    } catch (e) {
      setTests((t) => ({ ...t, [s.name]: { ok: false, seconds: 0, error: errText(e) } }));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <ModelHeading
        title="The coach's language model"
        does="Writes the coach's advice — the rest cards' wording — from facts the platform checked; every piece of advice records which model wrote it."
        learns="nothing here — it's chosen, not trained: pick the computer and the model, and compare them on a recorded session."
      />
      <p className="px-1 text-xs text-neutral-500">Switching takes effect on the next advice request — no restart.</p>

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
          const shownModel = picked[s.name] ?? s.model;
          const options = s.models.includes(s.model) ? s.models : [s.model, ...s.models];
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
                <div className="flex items-center justify-between gap-2">
                  <dt className="text-neutral-500">Model</dt>
                  <dd className="min-w-0">
                    {s.models.length > 0 ? (
                      <select
                        value={shownModel}
                        disabled={busy !== null}
                        onChange={(e) => {
                          const m = e.target.value;
                          // The one in use switches at once; another setup's waits for "Use this one".
                          if (s.active) {
                            if (m !== s.model) choose(s, m);
                          } else {
                            setPicked((p) => ({ ...p, [s.name]: m }));
                          }
                        }}
                        className="max-w-[12rem] truncate rounded-lg border border-white/10 bg-neutral-900 px-2 py-1 font-mono text-xs text-neutral-200"
                      >
                        {options.map((m) => (
                          <option key={m} value={m}>
                            {m}
                            {m === s.configured_model ? " (.env)" : ""}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <span className="font-mono text-neutral-200">{s.model}</span>
                    )}
                  </dd>
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

      {/* Comparisons read the sessions' facts: researchers only (ADR-058). */}
      {user?.is_researcher && st && st.setups.some((s) => s.models.length > 0) && (
        <ModelCompare setups={st.setups} onChosen={() => void load()} />
      )}
    </div>
  );
}

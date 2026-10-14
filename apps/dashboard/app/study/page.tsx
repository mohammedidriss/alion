"use client";

/**
 * The appropriate-reliance study (ADR-026; adapted from the Proposal V2 test build).
 *
 * Reviewers — coaches and referees a researcher enrolled — get one step at a time
 * from the server: trust check-ins and frozen advisories, each with its evidence,
 * to follow, adjust or reject. Nothing here tells them whether an advisory was
 * correct. Researchers enrol reviewers, add adjudicated advisories and export.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { SafetyBoundary } from "@/components/SafetyBoundary";
import {
  api,
  type RelianceDecision,
  type StudyAdvisory,
  type StudyInstrument,
  type StudyMe,
  type StudyReviewer,
  type StudySnapshotIndex,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

/** "403 {"detail":"…"}" → "…" */
function detail(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  const m = raw.match(/^(\d{3}) ([\s\S]*)$/);
  if (!m) return raw;
  try {
    const d = JSON.parse(m[2]).detail;
    return typeof d === "string" ? d : raw;
  } catch {
    return raw;
  }
}

export default function StudyPage() {
  const { user } = useAuth();
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header className="space-y-2">
        <h1 className="text-2xl font-semibold">Advisory review study</h1>
        <p className="text-sm text-neutral-300">
          Recorded training sessions, reviewed offline: read an AI advisory, open its evidence if
          you want to, and decide whether you would follow, adjust or reject it. This is research,
          not live coaching.
        </p>
        <SafetyBoundary />
      </header>
      {user?.is_researcher && <ResearcherPanel />}
      <ReviewerFlow researcher={!!user?.is_researcher} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Reviewer
// ---------------------------------------------------------------------------

function ReviewerFlow({ researcher }: { researcher: boolean }) {
  const [me, setMe] = useState<StudyMe | null>(null);
  const [blocked, setBlocked] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .studyMe()
      .then((m) => {
        setMe(m);
        setBlocked(null);
      })
      .catch((e) => setBlocked(detail(e)));
  }, []);
  useEffect(() => load(), [load]);

  if (blocked) {
    // A researcher who isn't also a reviewer doesn't need the message.
    if (researcher) return null;
    return (
      <section className="card space-y-2">
        <h2 className="text-lg font-semibold">Not enrolled yet</h2>
        <p className="text-sm text-neutral-300">{blocked}</p>
      </section>
    );
  }
  if (!me) return <p className="text-sm text-neutral-400">Loading…</p>;

  const step = me.step;
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Your review</h2>
        <span className="text-sm text-neutral-300">
          Study code <b className="text-neutral-100">{me.reviewer_code}</b> ·{" "}
          {me.decisions} of {me.total} advisories done
        </span>
      </div>
      {err && <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>}
      {!me.ready ? (
        <div className="card text-sm text-neutral-300">
          The study isn&apos;t open yet — the questionnaire is still being set up. The researcher will
          let you know when to start.
        </div>
      ) : step.kind === "survey" && step.instrument ? (
        <CheckIn
          label={step.label}
          instrument={step.instrument}
          onDone={() => {
            setErr(null);
            load();
          }}
          onError={setErr}
        />
      ) : step.kind === "trial" && step.advisory ? (
        <Advisory
          key={step.advisory.id}
          label={step.label}
          advisory={step.advisory}
          onDone={() => {
            setErr(null);
            load();
          }}
          onError={setErr}
        />
      ) : (
        <div className="card space-y-1">
          <h3 className="text-base font-semibold">All done — thank you</h3>
          <p className="text-sm text-neutral-300">
            Every advisory and check-in is recorded under your study code.
          </p>
        </div>
      )}
    </section>
  );
}

function CheckIn({
  label,
  instrument,
  onDone,
  onError,
}: {
  label: string;
  instrument: StudyInstrument;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const [scores, setScores] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const items = [...instrument.distrust, ...instrument.trust];
  const complete = items.every((i) => scores[i.id] != null);
  const range = Array.from(
    { length: instrument.scale.max - instrument.scale.min + 1 },
    (_, k) => instrument.scale.min + k,
  );

  const submit = async () => {
    setBusy(true);
    try {
      await api.studySubmitSurvey({
        trust_items: Object.fromEntries(instrument.trust.map((i) => [i.id, scores[i.id]])),
        distrust_items: Object.fromEntries(instrument.distrust.map((i) => [i.id, scores[i.id]])),
      });
      onDone();
    } catch (e) {
      onError(detail(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card space-y-4">
      <div>
        <h3 className="text-base font-semibold">{label}</h3>
        <p className="mt-1 text-sm text-neutral-300">
          How much does each statement fit the AI advisories you review? Here, &ldquo;the
          system&rdquo; means those advisories. {instrument.scale.min} = {instrument.scale.low},{" "}
          {instrument.scale.max} = {instrument.scale.high}.
        </p>
      </div>
      <ol className="space-y-3">
        {items.map((it, n) => (
          <li key={it.id} className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <p className="text-sm text-neutral-100">
              {n + 1}. {it.text}
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5" role="radiogroup" aria-label={it.text}>
              {range.map((v) => (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={scores[it.id] === v}
                  onClick={() => setScores((s) => ({ ...s, [it.id]: v }))}
                  className={`h-9 w-9 rounded-lg border text-sm ${
                    scores[it.id] === v
                      ? "border-emerald-400 bg-emerald-500/20 text-white"
                      : "border-white/15 text-neutral-300 hover:bg-white/5"
                  }`}
                >
                  {v}
                </button>
              ))}
            </div>
          </li>
        ))}
      </ol>
      <button
        onClick={submit}
        disabled={!complete || busy}
        className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-40"
      >
        {busy ? "Saving…" : complete ? "Save check-in" : `Answer all ${items.length} statements`}
      </button>
    </div>
  );
}

const DECISIONS: { value: RelianceDecision; label: string; desc: string }[] = [
  { value: "follow", label: "Follow", desc: "I would use this advice as it is." },
  { value: "adjust", label: "Adjust", desc: "I would use part of it, or change it." },
  { value: "reject", label: "Reject", desc: "I would not use this advice." },
];

function seconds(ms: number | null): string {
  return ms == null ? "" : `${(ms / 1000).toFixed(1)} s`;
}

function Advisory({
  label,
  advisory,
  onDone,
  onError,
}: {
  label: string;
  advisory: StudyAdvisory;
  onDone: () => void;
  onError: (m: string) => void;
}) {
  const shownAt = useRef(performance.now()); // decision time runs from first sight
  const opened = useRef(new Set<string>());
  const [rationale, setRationale] = useState("");
  const [busy, setBusy] = useState(false);

  const openEvidence = (claimId: string) => {
    if (opened.current.has(claimId)) return;
    opened.current.add(claimId);
    api.studyOpenEvidence(claimId).catch((e) => onError(detail(e)));
  };

  const decide = async (decision: RelianceDecision) => {
    setBusy(true);
    try {
      await api.studyDecide(advisory.id, {
        decision,
        response_ms: Math.max(0, Math.round(performance.now() - shownAt.current)),
        rationale: rationale.trim() || undefined,
      });
      onDone();
    } catch (e) {
      onError(detail(e));
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="card space-y-3">
        <p className="text-xs font-medium uppercase tracking-wider text-neutral-400">{label}</p>
        <h3 className="text-lg font-semibold">{advisory.summary}</h3>
        <ul className="space-y-1.5 text-sm text-neutral-200">
          {advisory.action_items.map((a) => (
            <li key={a}>• {a}</li>
          ))}
        </ul>
      </div>

      <div className="card space-y-3">
        <div>
          <h3 className="text-base font-semibold">Evidence</h3>
          <p className="text-sm text-neutral-300">
            Each claim, with the recorded data behind it. Open any you want to check.
          </p>
        </div>
        {advisory.claims.map((c) => (
          <details
            key={c.id}
            className="rounded-xl border border-white/10 bg-white/[0.02] p-3"
            onToggle={(e) => {
              if (e.currentTarget.open) openEvidence(c.id);
            }}
          >
            <summary className="cursor-pointer text-sm font-medium text-neutral-100">{c.claim_text}</summary>
            <dl className="mt-3 grid gap-2 text-xs text-neutral-300 sm:grid-cols-3">
              <div>
                <dt className="text-neutral-500">Source</dt>
                <dd>{c.source_stream}</dd>
              </div>
              <div>
                <dt className="text-neutral-500">When</dt>
                <dd>
                  {c.source_start_ms != null
                    ? `${seconds(c.source_start_ms)}${c.source_end_ms != null ? ` – ${seconds(c.source_end_ms)}` : ""}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-neutral-500">Evidence quality</dt>
                <dd>{c.evidence_quality}</dd>
              </div>
              <div className="sm:col-span-3">
                <dt className="text-neutral-500">Recorded values</dt>
                <dd className="mt-1 grid gap-x-4 gap-y-0.5 rounded bg-black/30 p-2 font-mono sm:grid-cols-2">
                  {Object.entries(c.evidence).map(([k, v]) => (
                    <span key={k}>
                      {k}: <span className="text-neutral-100">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
                    </span>
                  ))}
                </dd>
              </div>
            </dl>
          </details>
        ))}
      </div>

      <div className="card space-y-3">
        <div>
          <h3 className="text-base font-semibold">Your decision</h3>
          <p className="text-sm text-neutral-300">
            What would you do with this advice in training? Your choice is final once you press it.
          </p>
        </div>
        <label className="block text-sm text-neutral-200">
          Why (optional)
          <textarea
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            rows={3}
            maxLength={2000}
            className="mt-1.5 w-full rounded-xl border border-white/10 bg-black/30 p-3 text-sm outline-none focus:border-emerald-500/50"
          />
        </label>
        <div className="grid gap-2 sm:grid-cols-3">
          {DECISIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => void decide(d.value)}
              disabled={busy}
              className="rounded-xl border border-white/15 px-4 py-3 text-left hover:bg-white/5 disabled:opacity-40"
            >
              <span className="block text-sm font-semibold text-neutral-100">{d.label}</span>
              <span className="block text-xs text-neutral-400">{d.desc}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Researcher
// ---------------------------------------------------------------------------

const TEMPLATE = {
  session_id: "<a session id>",
  payload_mode: "fused",
  model_id: "gemma3:4b",
  prompt_version: "v3",
  prompt_text: "<the prompt that produced the advice>",
  input_payload: { round: 1 },
  summary: "<the advice summary>",
  action_items: ["<action 1>", "<action 2>", "<action 3>"],
  correctness: "correct",
  adjudication_note: "<how the adjudicators decided>",
  claims: [
    {
      claim_text: "<one claim in the advice>",
      evidence: { t_ms: 0 },
      source_stream: "cv",
      source_start_ms: 0,
      source_end_ms: 1000,
      evidence_quality: "validated",
    },
  ],
};

function ResearcherPanel() {
  const [instrument, setInstrument] = useState<StudyInstrument | null>(null);
  const [reviewers, setReviewers] = useState<StudyReviewer[]>([]);
  const [snapshots, setSnapshots] = useState<StudySnapshotIndex[]>([]);
  const [email, setEmail] = useState("");
  const [json, setJson] = useState(JSON.stringify(TEMPLATE, null, 2));
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.studyInstrument().then(setInstrument).catch((e) => setMsg(detail(e)));
    api.studyReviewers().then(setReviewers).catch((e) => setMsg(detail(e)));
    api.studySnapshots().then(setSnapshots).catch((e) => setMsg(detail(e)));
  }, []);
  useEffect(() => load(), [load]);

  const enrol = async () => {
    setBusy(true);
    try {
      const r = await api.studyEnrol(email.trim());
      setMsg(`Enrolled ${r.name} as ${r.reviewer_code}.`);
      setEmail("");
      load();
    } catch (e) {
      setMsg(detail(e));
    } finally {
      setBusy(false);
    }
  };

  const addAdvisory = async () => {
    setBusy(true);
    try {
      const r = await api.studyAddSnapshot(JSON.parse(json));
      setMsg(`Advisory frozen (output ${r.output_sha256.slice(0, 10)}…).`);
      load();
    } catch (e) {
      setMsg(e instanceof SyntaxError ? `Not valid JSON: ${e.message}` : detail(e));
    } finally {
      setBusy(false);
    }
  };

  const download = async () => {
    try {
      const data = await api.studyExport();
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `reliance-study-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setMsg(detail(e));
    }
  };

  return (
    <section className="space-y-4 rounded-2xl border border-sky-500/30 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">Researcher</h2>
        <button
          onClick={download}
          className="rounded-lg border border-white/15 px-3 py-1.5 text-xs font-medium text-neutral-200 hover:bg-white/5"
        >
          Export results (JSON)
        </button>
      </div>
      {msg && <p className="text-sm text-amber-200">{msg}</p>}

      <div className="card space-y-1 text-sm">
        <h3 className="text-base font-semibold">Questionnaire</h3>
        <p className="text-neutral-300">{instrument?.name ?? "…"}</p>
        {instrument && !instrument.ready && (
          <p className="text-amber-300">
            Not ready: paste your protocol&apos;s wording for each item into{" "}
            <code className="rounded bg-black/30 px-1">packages/api/services/reliance_trust_items.json</code>.
            Reviewers can&apos;t start until then.
          </p>
        )}
        {instrument?.ready && (
          <p className="text-emerald-300">
            Ready: {instrument.distrust.length} distrust and {instrument.trust.length} trust items.
          </p>
        )}
      </div>

      <div className="card space-y-3">
        <h3 className="text-base font-semibold">Reviewers</h3>
        <p className="text-xs text-neutral-400">
          Enrol a coach or referee account only after you have checked their signed consent form.
        </p>
        <div className="flex flex-wrap gap-2">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="their account email"
            className="min-w-[220px] flex-1 rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-sm outline-none focus:border-emerald-500/50"
          />
          <button
            onClick={enrol}
            disabled={busy || !email.includes("@")}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
          >
            Enrol
          </button>
        </div>
        {reviewers.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="text-left text-xs uppercase text-neutral-400">
                <tr>
                  <th className="py-1.5 pr-3">Code</th>
                  <th className="py-1.5 pr-3">Name</th>
                  <th className="py-1.5 pr-3">Role</th>
                  <th className="py-1.5 pr-3">Decisions</th>
                  <th className="py-1.5">Check-ins</th>
                </tr>
              </thead>
              <tbody>
                {reviewers.map((r) => (
                  <tr key={r.reviewer_code} className="border-t border-white/5">
                    <td className="py-2 pr-3 font-mono">{r.reviewer_code}</td>
                    <td className="py-2 pr-3">{r.name}</td>
                    <td className="py-2 pr-3 text-neutral-400">{r.role}</td>
                    <td className="py-2 pr-3 tabular-nums">{r.decisions}</td>
                    <td className="py-2 tabular-nums">{r.check_ins}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="card space-y-3">
        <h3 className="text-base font-semibold">Advisories ({snapshots.length})</h3>
        {snapshots.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[480px] text-sm">
              <thead className="text-left text-xs uppercase text-neutral-400">
                <tr>
                  <th className="py-1.5 pr-3">Frozen</th>
                  <th className="py-1.5 pr-3">Data</th>
                  <th className="py-1.5 pr-3">Model</th>
                  <th className="py-1.5 pr-3">Adjudicated</th>
                  <th className="py-1.5">Claims</th>
                </tr>
              </thead>
              <tbody>
                {snapshots.map((s) => (
                  <tr key={s.id} className="border-t border-white/5">
                    <td className="py-2 pr-3">{new Date(s.created_at).toLocaleDateString()}</td>
                    <td className="py-2 pr-3 uppercase">{s.payload_mode}</td>
                    <td className="py-2 pr-3 text-neutral-300">{s.model_id}</td>
                    <td className="py-2 pr-3">{s.correctness.replace("_", " ")}</td>
                    <td className="py-2 tabular-nums">{s.claims}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <details>
          <summary className="cursor-pointer text-sm font-medium text-neutral-200">Add an advisory (JSON)</summary>
          <p className="mt-2 text-xs text-neutral-400">
            Frozen as sent — no edit or delete. Its correctness is never shown to reviewers.
          </p>
          <textarea
            value={json}
            onChange={(e) => setJson(e.target.value)}
            rows={16}
            spellCheck={false}
            className="mt-2 w-full rounded-xl border border-white/10 bg-black/30 p-3 font-mono text-xs outline-none focus:border-emerald-500/50"
          />
          <button
            onClick={addAdvisory}
            disabled={busy}
            className="mt-2 rounded-xl border border-white/15 px-4 py-2 text-sm font-semibold text-neutral-100 hover:bg-white/5 disabled:opacity-40"
          >
            Freeze advisory
          </button>
        </details>
      </div>
    </section>
  );
}

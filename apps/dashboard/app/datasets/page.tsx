"use client";

/**
 * Datasets (ADR-013, ADR-057) — research recordings, kept apart from training
 * sessions: each dataset holds its participants (with consent) and their takes,
 * recorded to a protocol. Only data here: the models trained on it are on the AI
 * models page.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type DatasetSummary } from "@/lib/api";
import { PROTOCOL_PURPOSE } from "@/lib/protocols";

const PROTOCOLS = [
  { key: "rq2-v1", label: "RQ2 punch protocol" },
  { key: "", label: "Free recording (no protocol)" },
];


export default function DatasetsPage() {
  const [datasets, setDatasets] = useState<DatasetSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [showNew, setShowNew] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [protocol, setProtocol] = useState("rq2-v1");
  const [creating, setCreating] = useState(false);

  const load = () =>
    api
      .listDatasets()
      .then(setDatasets)
      .catch((e) => setErr(String(e)));

  useEffect(() => {
    load();
  }, []);

  const create = async () => {
    if (!name.trim() || creating) return;
    setCreating(true);
    setErr(null);
    try {
      await api.createDataset({
        name: name.trim(),
        description: description.trim() || undefined,
        protocol: protocol || undefined,
      });
      setName("");
      setDescription("");
      setShowNew(false);
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Datasets</h1>
          <p className="max-w-2xl text-sm text-neutral-400">
            Research recordings with consenting participants, made to a protocol and kept apart from training
            sessions. The models trained on them are on the{" "}
            <Link href="/ai-model" className="text-emerald-300 underline hover:text-emerald-200">
              AI models
            </Link>{" "}
            page.
          </p>
        </div>
        <button
          onClick={() => setShowNew((v) => !v)}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400"
        >
          + New dataset
        </button>
      </header>

      {showNew && (
        <div className="card space-y-3">
          <h2 className="text-base font-semibold">New dataset</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm">
              <span className="text-neutral-400">Name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="RQ2 punch dataset — pilot"
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2"
              />
            </label>
            <label className="block text-sm">
              <span className="text-neutral-400">Protocol</span>
              <select
                value={protocol}
                onChange={(e) => setProtocol(e.target.value)}
                className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2"
              >
                {PROTOCOLS.map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="block text-sm">
            <span className="text-neutral-400">Description (optional)</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2"
            />
          </label>
          <div className="flex gap-2">
            <button
              onClick={create}
              disabled={!name.trim() || creating}
              className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
            >
              {creating ? "Creating…" : "Create dataset"}
            </button>
            <button
              onClick={() => setShowNew(false)}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm text-neutral-300 hover:bg-white/5"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {err && <p className="text-sm text-red-400">{err}</p>}

      {datasets === null ? (
        <p className="text-sm text-neutral-500">Loading…</p>
      ) : datasets.length === 0 ? (
        <div className="card text-sm text-neutral-400">
          <p className="font-medium text-neutral-200">No datasets yet</p>
          <p className="mt-1">
            Create one, add yourself as the self-recording researcher, and record your first
            take. Other fighters can be added once their IRB consent is signed.
          </p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {datasets.map((d) => (
            <Link
              key={d.id}
              href={`/datasets/${d.id}`}
              className="card block transition-colors hover:border-white/15"
            >
              <div className="flex items-start justify-between gap-2">
                <h2 className="text-base font-semibold">{d.name}</h2>
                {d.protocol && (
                  <span className="pill shrink-0 bg-violet-900/50 text-violet-200">{d.protocol}</span>
                )}
              </div>
              {(d.description || (d.protocol && PROTOCOL_PURPOSE[d.protocol])) && (
                <p className="mt-1 line-clamp-3 text-xs text-neutral-400">
                  {d.description || (d.protocol ? PROTOCOL_PURPOSE[d.protocol] : "")}
                </p>
              )}
              <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-400">
                <span>
                  <strong className="text-neutral-100">{d.participants}</strong> participant{d.participants === 1 ? "" : "s"}
                </span>
                <span>
                  <strong className="text-neutral-100">{d.completed_takes}</strong> takes done
                </span>
                {!!d.in_progress_takes && (
                  <span>
                    <strong className="text-neutral-100">{d.in_progress_takes}</strong> recording now
                  </span>
                )}
                {!!d.discarded_takes && <span>{d.discarded_takes} discarded (kept)</span>}
              </div>
              {d.last_recorded_at && (
                <p className="mt-1 text-[11px] text-neutral-500">
                  Last recorded {new Date(d.last_recorded_at).toLocaleDateString()}
                </p>
              )}
              {!!d.stuck_takes && (
                <p className="mt-2 rounded-lg bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
                  {d.stuck_takes} take{d.stuck_takes === 1 ? " is" : "s are"} still marked recording with nothing
                  recording — check {d.stuck_takes === 1 ? "it" : "them"}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

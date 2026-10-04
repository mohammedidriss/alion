"use client";

/**
 * One dataset (ADR-013): its participants with their consent, and every recorded
 * take with what it captured. "Record take" is only offered when consent allows
 * it — the researcher recording himself (`self`) or a signed IRB consent.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  api,
  type Consent,
  type DatasetDetail,
  type DatasetParticipant,
  type Fighter,
  type Take,
} from "@/lib/api";

const CONSENT: Record<Consent, { label: string; cls: string }> = {
  self: { label: "Self (researcher)", cls: "bg-sky-900/60 text-sky-200" },
  irb_signed: { label: "IRB signed", cls: "bg-emerald-900/60 text-emerald-200" },
  pending: { label: "Pending", cls: "bg-amber-900/60 text-amber-200" },
  withdrawn: { label: "Withdrawn", cls: "bg-red-900/60 text-red-200" },
};

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

function duration(ms: number): string {
  if (!ms) return "—";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function DatasetPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [ds, setDs] = useState<DatasetDetail | null>(null);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () =>
    api
      .getDataset(params.id)
      .then(setDs)
      .catch((e) => setErr(errText(e)));

  useEffect(() => {
    load();
    api.listFighters().then(setFighters).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  const record = async (fighterId: string) => {
    setBusy(fighterId);
    setErr(null);
    try {
      const take = await api.createTake(params.id, fighterId);
      router.push(`/datasets/${params.id}/takes/${take.id}`);
    } catch (e) {
      setErr(errText(e));
      setBusy(null);
    }
  };

  const setConsent = async (p: DatasetParticipant, consent: Consent) => {
    setErr(null);
    try {
      setDs(
        await api.setParticipant(params.id, {
          fighter_id: p.fighter_id,
          consent,
          consent_date: p.consent_date,
          irb_ref: p.irb_ref,
          notes: p.notes,
        }),
      );
    } catch (e) {
      setErr(errText(e));
    }
  };

  if (!ds) {
    return (
      <div className="px-4 py-5 sm:px-8 sm:py-6 text-sm text-neutral-400">
        {err ?? "Loading…"}
      </div>
    );
  }

  const takes = ds.takes;
  const kept = takes.filter((t) => t.status !== "discarded");

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <Link href="/datasets" className="text-sm text-neutral-400 hover:text-neutral-200">
        ← Datasets
      </Link>
      <header>
        <div className="flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold">{ds.name}</h1>
          {ds.protocol && <span className="pill bg-violet-900/50 text-violet-200">{ds.protocol}</span>}
        </div>
        {ds.description && <p className="mt-1 text-sm text-neutral-400">{ds.description}</p>}
      </header>

      {err && (
        <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">
          {err}
        </p>
      )}

      {/* Participants */}
      <section className="card space-y-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-base font-semibold">Participants</h2>
          <span className="text-xs text-neutral-500">
            Record only with self or IRB consent (ADR-002)
          </span>
        </div>
        {ds.participants.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No participants yet. Add yourself as the self-recording researcher to start.
          </p>
        ) : (
          <div className="divide-y divide-white/5">
            {ds.participants.map((p) => (
              <div key={p.fighter_id} className="flex flex-wrap items-center gap-3 py-2.5">
                <div className="min-w-[10rem] flex-1">
                  <div className="font-medium">{p.name}</div>
                  <div className="text-xs text-neutral-500">
                    {p.stance ?? "stance unknown"} · {p.takes} take{p.takes === 1 ? "" : "s"}
                    {p.irb_ref && <> · IRB {p.irb_ref}</>}
                  </div>
                </div>
                <select
                  value={p.consent}
                  onChange={(e) => setConsent(p, e.target.value as Consent)}
                  className={`rounded-full border-0 px-3 py-1 text-xs font-medium ${CONSENT[p.consent].cls}`}
                  aria-label={`Consent for ${p.name}`}
                >
                  {(Object.keys(CONSENT) as Consent[]).map((c) => (
                    <option key={c} value={c}>
                      {CONSENT[c].label}
                    </option>
                  ))}
                </select>
                <button
                  onClick={() => record(p.fighter_id)}
                  disabled={!p.may_record || busy !== null}
                  title={p.may_record ? undefined : "Needs self or IRB-signed consent"}
                  className="rounded-xl bg-red-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-500 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
                >
                  {busy === p.fighter_id ? "Opening…" : "● Record take"}
                </button>
              </div>
            ))}
          </div>
        )}
        <AddParticipant
          fighters={fighters.filter((f) => !ds.participants.some((p) => p.fighter_id === f.id))}
          onAdd={async (fighterId, consent, irbRef) => {
            setErr(null);
            try {
              setDs(
                await api.setParticipant(params.id, {
                  fighter_id: fighterId,
                  consent,
                  irb_ref: irbRef || null,
                  consent_date: consent === "irb_signed" ? new Date().toISOString().slice(0, 10) : null,
                }),
              );
            } catch (e) {
              setErr(errText(e));
            }
          }}
        />
      </section>

      {/* Takes */}
      <section className="card space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="flex items-baseline gap-3">
            <h2 className="text-base font-semibold">Takes</h2>
            <span className="text-xs text-neutral-500">
              {kept.filter((t) => t.status === "completed").length} completed
            </span>
          </div>
        </div>
        {takes.length === 0 ? (
          <p className="text-sm text-neutral-500">No takes recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-xs text-neutral-500">
                <tr>
                  <th className="py-2 font-normal">Recorded</th>
                  <th className="font-normal">Fighter</th>
                  <th className="font-normal">Status</th>
                  <th className="font-normal">Length</th>
                  <th className="font-normal">Video</th>
                  <th className="font-normal">Wrist IMU</th>
                  <th className="font-normal">Heart</th>
                  <th className="font-normal">Labels</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {takes.map((t) => (
                  <TakeRow key={t.id} take={t} datasetId={ds.id} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function TakeRow({ take, datasetId }: { take: Take; datasetId: string }) {
  const clips = take.data.clips ?? [];
  const dim = take.status === "discarded" ? "opacity-50" : "";
  const status = {
    recording: "bg-amber-900/60 text-amber-200",
    completed: "bg-emerald-900/60 text-emerald-200",
    discarded: "bg-neutral-800 text-neutral-400",
  }[take.status];
  return (
    <tr className={dim}>
      <td className="py-2">
        <Link
          href={`/datasets/${datasetId}/takes/${take.id}`}
          className="text-sky-300 hover:text-sky-200"
        >
          {new Date(take.started_at).toLocaleString()}
        </Link>
      </td>
      <td>{take.fighter_name ?? "—"}</td>
      <td>
        <span className={`pill ${status}`}>{take.status}</span>
      </td>
      <td className="tabular-nums">{duration(take.duration_ms)}</td>
      <td>{clips.length ? `${clips.length} cam${clips.length > 1 ? "s" : ""}` : "—"}</td>
      <td className="tabular-nums">{take.data.imu_rows ? take.data.imu_rows.toLocaleString() : "—"}</td>
      <td className="tabular-nums">{take.data.hr_rows ? `${take.data.hr_rows} beats` : "—"}</td>
      <td className="tabular-nums">{take.data.labels != null ? take.data.labels : "—"}</td>
    </tr>
  );
}

function AddParticipant({
  fighters,
  onAdd,
}: {
  fighters: Fighter[];
  onAdd: (fighterId: string, consent: Consent, irbRef: string) => Promise<void>;
}) {
  const [fighterId, setFighterId] = useState("");
  const [consent, setConsent] = useState<Consent>("self");
  const [irbRef, setIrbRef] = useState("");
  if (fighters.length === 0) return null;
  return (
    <div className="flex flex-wrap items-end gap-2 border-t border-white/5 pt-4">
      <label className="text-sm">
        <span className="block text-xs text-neutral-500">Add fighter</span>
        <select
          value={fighterId}
          onChange={(e) => setFighterId(e.target.value)}
          className="mt-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2"
        >
          <option value="">Choose…</option>
          {fighters.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      </label>
      <label className="text-sm">
        <span className="block text-xs text-neutral-500">Consent</span>
        <select
          value={consent}
          onChange={(e) => setConsent(e.target.value as Consent)}
          className="mt-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2"
        >
          {(Object.keys(CONSENT) as Consent[]).map((c) => (
            <option key={c} value={c}>
              {CONSENT[c].label}
            </option>
          ))}
        </select>
      </label>
      {consent === "irb_signed" && (
        <label className="text-sm">
          <span className="block text-xs text-neutral-500">IRB reference</span>
          <input
            value={irbRef}
            onChange={(e) => setIrbRef(e.target.value)}
            placeholder="e.g. IRB-2026-041"
            className="mt-1 rounded-lg border border-white/10 bg-black/30 px-3 py-2"
          />
        </label>
      )}
      <button
        onClick={async () => {
          if (!fighterId) return;
          await onAdd(fighterId, consent, irbRef);
          setFighterId("");
          setIrbRef("");
        }}
        disabled={!fighterId}
        className="rounded-xl border border-white/15 px-4 py-2 text-sm hover:bg-white/5 disabled:opacity-40"
      >
        Add
      </button>
    </div>
  );
}

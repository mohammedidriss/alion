"use client";

/**
 * Take recording screen (ADR-013). The same capture tools as a training session —
 * live reader, cameras (laptop + phones via the QR), wrist IMUs and Polar — but
 * everything lands in the take's folder, never in a session. No Pause: protocol
 * blocks need one unbroken timeline. After Stop & save it shows what was captured.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { JoinQrCard } from "@/components/JoinQrCard";
import { LiveReader } from "@/components/LiveReader";
import { MulticamPanel } from "@/components/MulticamPanel";
import { MulticamRecordings } from "@/components/MulticamRecordings";
import { PolarH10Card } from "@/components/PolarH10Card";
import { AutoProtocol } from "@/components/AutoProtocol";
import { ProtocolCard } from "@/components/ProtocolCard";
import { api, type Take } from "@/lib/api";

function duration(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function TakePage({ params }: { params: { id: string; takeId: string } }) {
  const router = useRouter();
  const [take, setTake] = useState<Take | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);

  const load = useCallback(
    () =>
      api
        .getTake(params.takeId)
        .then(setTake)
        .catch((e) => setErr(String(e))),
    [params.takeId],
  );

  useEffect(() => {
    load();
  }, [load]);

  if (!take) {
    return (
      <div className="px-4 py-5 text-sm text-neutral-400 sm:px-8 sm:py-6">{err ?? "Loading…"}</div>
    );
  }

  const recording = take.status === "recording";
  const status = {
    recording: "bg-amber-900/60 text-amber-200",
    completed: "bg-emerald-900/60 text-emerald-200",
    discarded: "bg-neutral-800 text-neutral-400",
  }[take.status];

  return (
    <div className="space-y-6 px-4 py-5 sm:px-8 sm:py-6">
      <Link href={`/datasets/${params.id}`} className="text-sm text-neutral-400 hover:text-neutral-200">
        ← {take.dataset_name ?? "Dataset"}
      </Link>

      <header className="flex flex-wrap items-center justify-between gap-4 lg:grid lg:grid-cols-[1fr_auto_1fr]">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold">Take · {take.fighter_name}</h1>
            <span className={`pill ${status}`}>{take.status}</span>
            {/* Pair the heart-rate strap here — it streams with the cameras. */}
            {recording && <PolarH10Card />}
          </div>
          <p className="text-xs text-neutral-500">
            {new Date(take.started_at).toLocaleString()} · dataset recording, not a training
            session
          </p>
        </div>
        {recording ? <JoinQrCard takeId={take.id} compact /> : <div className="hidden lg:block" />}
        <div className="lg:justify-self-end">
          {take.status !== "discarded" &&
            (confirmDiscard ? (
              <span className="flex items-center gap-2 text-sm">
                <span className="text-neutral-400">Exclude this take from the dataset?</span>
                <button
                  onClick={async () => {
                    setTake(await api.discardTake(take.id));
                    setConfirmDiscard(false);
                  }}
                  className="rounded-lg bg-red-600 px-3 py-1 text-white hover:bg-red-500"
                >
                  Discard
                </button>
                <button
                  onClick={() => setConfirmDiscard(false)}
                  className="rounded-lg border border-white/10 px-3 py-1 text-neutral-300"
                >
                  Keep
                </button>
              </span>
            ) : (
              <button
                onClick={() => setConfirmDiscard(true)}
                className="text-sm text-red-400 hover:text-red-300"
              >
                Discard take
              </button>
            ))}
        </div>
      </header>

      {err && <p className="text-sm text-red-400">{err}</p>}

      {recording && (
        <div className="grid items-start gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          <div className="space-y-6">
            <LiveReader takeId={take.id} fighterId={take.fighter_id} />
            {/* Protocol blocks — run automatically, or by hand with Start / End. */}
            <ProtocolArea takeId={take.id} />
          </div>
          <MulticamPanel
            take={take}
            defaultLaptop
            onFinished={load}
            onDelete={async () => {
              // Delete for good, then a fresh take for the same fighter — the linked
              // phones follow it there.
              await api.deleteTake(take.id);
              const next = await api.createTake(take.dataset_id, take.fighter_id);
              router.replace(`/datasets/${params.id}/takes/${next.id}`);
            }}
          />
        </div>
      )}

      {take.status === "discarded" && (
        <p className="rounded-xl border border-white/10 p-3 text-sm text-neutral-400">
          Discarded — excluded from the dataset. Its files are kept on disk.
        </p>
      )}

      {/* Keyed on status so the clips reload when Stop completes the take. */}
      <MulticamRecordings key={take.status} takeId={take.id} />

      {!recording && <TakeData take={take} />}
      {/* After Stop: the recorded blocks and labels, read-only. */}
      {!recording && <ProtocolCard takeId={take.id} readOnly />}
    </div>
  );
}

function TakeData({ take }: { take: Take }) {
  const d = take.data;
  const items: [string, string][] = [
    ["Length", take.duration_ms ? duration(take.duration_ms) : "—"],
    ["Cameras", d.clips?.length ? String(d.clips.length) : "—"],
    ["Wrist IMU samples", d.imu_rows ? d.imu_rows.toLocaleString() : "—"],
    ["Heartbeats", d.hr_rows ? d.hr_rows.toLocaleString() : "—"],
    ["Labelled punches", d.labels != null ? String(d.labels) : "not labelled yet"],
  ];
  return (
    <section className="card">
      <h2 className="text-base font-semibold">Captured</h2>
      <dl className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-5">
        {items.map(([k, v]) => (
          <div key={k} className="rounded-xl border border-white/5 bg-black/20 p-3">
            <dt className="text-[10px] uppercase tracking-wide text-neutral-500">{k}</dt>
            <dd className="mt-1 text-lg font-semibold tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

type ProtocolMode = "auto" | "manual";
const MODE_KEY = "alion.protocolMode";

/** Automatic (hands-free, beep-paced) or manual (Start / End per block). The
 *  manual card stays visible read-only in automatic mode for the block results. */
function ProtocolArea({ takeId }: { takeId: string }) {
  const [mode, setMode] = useState<ProtocolMode>("auto");
  useEffect(() => {
    try {
      const m = localStorage.getItem(MODE_KEY);
      if (m === "auto" || m === "manual") setMode(m);
    } catch {
      /* default */
    }
  }, []);
  const choose = (m: ProtocolMode) => {
    setMode(m);
    try {
      localStorage.setItem(MODE_KEY, m);
    } catch {
      /* not persisted */
    }
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 rounded-xl border border-white/10 p-0.5 text-xs" role="tablist">
        {(["auto", "manual"] as const).map((m) => (
          <button
            key={m}
            role="tab"
            aria-selected={mode === m}
            onClick={() => choose(m)}
            className={`rounded-lg px-3 py-1.5 font-medium ${
              mode === m ? "bg-white/10 text-white" : "text-neutral-400 hover:text-neutral-200"
            }`}
          >
            {m === "auto" ? "Automatic" : "Manual (Start / End)"}
          </button>
        ))}
      </div>
      {mode === "auto" ? (
        <>
          <AutoProtocol takeId={takeId} />
          <ProtocolCard takeId={takeId} readOnly />
        </>
      ) : (
        <ProtocolCard takeId={takeId} />
      )}
    </div>
  );
}

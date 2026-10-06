"use client";

/**
 * Take recording screen (ADR-013). The same capture tools as a training session —
 * live reader, cameras (laptop + phones via the QR), wrist IMUs and Polar — but
 * everything lands in the take's folder, never in a session. No Pause: protocol
 * blocks need one unbroken timeline. After Stop & save it shows what was captured.
 *
 * One block per take: a take with a `block` runs just that block, saves itself
 * when the block ends, is checked (BlockSitting), and — in a sitting (?sitting=1)
 * — hands over to the next block's take, which starts by itself after the rest.
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
import { TakeCrossCheckCard } from "@/components/TakeCrossCheckCard";
import { BlockSitting, blockHref } from "@/components/BlockSitting";
import { api, type ProtocolBlockSpec, type Take } from "@/lib/api";

// How many cameras the last block of this sitting recorded with — the next block
// waits for that many before it starts by itself.
const SITTING_CAMERAS_KEY = "alion.sittingCameras";

function duration(ms: number): string {
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export default function TakePage({ params }: { params: { id: string; takeId: string } }) {
  const router = useRouter();
  const [take, setTake] = useState<Take | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [plan, setPlan] = useState<ProtocolBlockSpec[]>([]);
  const [stopSignal, setStopSignal] = useState(0);
  // Sitting mode (from the URL): keep going block after block; `rest` is when the
  // rest before this block ends (it starts by itself then).
  const [sitting, setSitting] = useState<{ on: boolean; restUntil: number | null }>({
    on: false,
    restUntil: null,
  });
  const [, setTick] = useState(0);
  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const rest = Number(q.get("rest"));
    setSitting({ on: q.get("sitting") === "1", restUntil: Number.isFinite(rest) && rest > 0 ? rest : null });
    api.protocolPlan().then(setPlan).catch(() => {});
  }, [params.takeId]);
  useEffect(() => {
    if (!sitting.restUntil) return;
    const id = setInterval(() => setTick((t) => t + 1), 500);
    return () => clearInterval(id);
  }, [sitting.restUntil]);

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

  // A draft becomes the recording when Start all cameras is pressed, and an
  // uploading take completes when the last camera's video lands — pick both up.
  const draft = take?.status === "recording" && !take.started;
  const uploading = take?.status === "uploading";
  useEffect(() => {
    if (!draft && !uploading) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [draft, uploading, load]);

  if (!take) {
    return (
      <div className="px-4 py-5 text-sm text-neutral-400 sm:px-8 sm:py-6">{err ?? "Loading…"}</div>
    );
  }

  // Uploading keeps the capture panel up: the cameras are still sending their video.
  const recording = take.status === "recording" || take.status === "uploading";
  const blockIdx = take.block ? plan.findIndex((s) => s.key === take.block) : -1;
  const blockSpec = blockIdx >= 0 ? plan[blockIdx] : undefined;
  const restLeft = sitting.restUntil ? Math.max(0, sitting.restUntil - Date.now()) : 0;
  let sittingCameras = 0;
  try {
    sittingCameras = Number(sessionStorage.getItem(SITTING_CAMERAS_KEY)) || 0;
  } catch {
    /* no storage — start by hand */
  }
  // The next block of a sitting starts by itself: after the rest, once the same
  // cameras are back.
  const autoStart =
    sitting.on && sitting.restUntil !== null && draft && restLeft === 0 && sittingCameras > 0
      ? { cameras: sittingCameras }
      : undefined;
  const status = draft
    ? "bg-sky-900/60 text-sky-200"
    : {
        recording: "bg-amber-900/60 text-amber-200",
        uploading: "animate-pulse bg-sky-900/60 text-sky-200",
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
            <h1 className="text-2xl font-semibold">
              {blockSpec ? `${blockSpec.title} · ` : take.block ? `${take.block} · ` : "Take · "}
              {take.fighter_name}
            </h1>
            {blockSpec && (
              <span className="text-xs text-neutral-500">
                block {blockIdx + 1} of {plan.length}
              </span>
            )}
            <span
              className={`pill ${status}`}
              title={draft ? "Not in the dataset until you press Start all cameras" : undefined}
            >
              {draft ? "not started" : take.status}
            </span>
            {/* Pair the heart-rate strap here — it streams with the cameras. */}
            {recording && <PolarH10Card />}
          </div>
          <p className="text-xs text-neutral-500">
            {draft && autoStart
              ? "Starts by itself as soon as the cameras and wrist sensors are back"
              : draft
                ? "Connect the cameras and sensors — the take is recorded and added to the dataset when you press Start all cameras"
                : `${new Date(take.started_at).toLocaleString()} · dataset recording, not a training session`}
          </p>
        </div>
        {recording ? <JoinQrCard takeId={take.id} compact /> : <div className="hidden lg:block" />}
        <div className="lg:justify-self-end">
          {take.status !== "discarded" &&
            !draft &&
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

      {draft && restLeft > 0 && (
        <div className="rounded-2xl border border-sky-500/30 bg-sky-950/30 p-4 text-center">
          <div className="text-xs uppercase tracking-widest text-sky-300">Rest</div>
          <div className="text-5xl font-bold tabular-nums text-sky-200">
            {Math.ceil(restLeft / 1000)}
          </div>
          <div className="mt-1 text-sm text-neutral-300">
            Next: {blockSpec?.title ?? take.block} — the cameras and sensors reconnect meanwhile
          </div>
        </div>
      )}

      {/* One block per take: once saved, check it and move on (or redo it). */}
      {take.block && take.status === "completed" && plan.length > 0 && (
        <BlockSitting take={take} plan={plan} sitting={sitting.on} />
      )}

      {recording && (
        <div className="grid items-start gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
          <div className="space-y-6">
            <LiveReader takeId={take.id} fighterId={take.fighter_id} />
            {take.block ? (
              <>
                {/* This take's block only: when it ends, the take saves itself. */}
                <AutoProtocol
                  takeId={take.id}
                  onlyBlock={take.block}
                  onBlockDone={() => setStopSignal((n) => n + 1)}
                />
                <ProtocolCard takeId={take.id} readOnly />
              </>
            ) : (
              // Protocol blocks — run automatically, or by hand with Start / End.
              <ProtocolArea takeId={take.id} />
            )}
          </div>
          <MulticamPanel
            take={take}
            defaultLaptop
            autoStart={autoStart}
            stopSignal={stopSignal}
            onStopping={(cameras) => {
              try {
                sessionStorage.setItem(SITTING_CAMERAS_KEY, String(cameras));
              } catch {
                /* the next block then starts by hand */
              }
              void load();
            }}
            onFinished={load}
            onDelete={async () => {
              // Delete for good, then a fresh take for the same fighter (and block) —
              // the linked phones follow it there.
              await api.deleteTake(take.id);
              const next = await api.createTake(take.dataset_id, take.fighter_id, take.block);
              router.replace(
                take.block && sitting.on
                  ? blockHref(params.id, next.id)
                  : `/datasets/${params.id}/takes/${next.id}`,
              );
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
      {/* How the wrist sensors and the cameras agree on this take's punches. */}
      {take.status === "completed" && <TakeCrossCheckCard takeId={take.id} />}
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

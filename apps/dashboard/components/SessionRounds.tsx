"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type AttachmentKind,
  type Session,
  type SessionAttachment,
} from "@/lib/api";

/**
 * Round configuration card — visible while the session is `pending`,
 * collapses to a compact summary once it has been started.
 *
 * Defaults match a typical 3×3-minute pro round (3 rounds, 180s, 60s rest)
 * if the user hasn't customised it.
 */
export function RoundConfigCard({
  session,
  onChange,
}: {
  session: Session;
  onChange: (s: Session) => void;
}) {
  const [rounds, setRounds] = useState<number>(session.round_count ?? 3);
  const [roundS, setRoundS] = useState<number>(session.round_duration_s ?? 3);
  const [restS, setRestS] = useState<number>(session.rest_duration_s ?? 3);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setRounds(session.round_count ?? 3);
    setRoundS(session.round_duration_s ?? 3);
    setRestS(session.rest_duration_s ?? 3);
  }, [session.round_count, session.round_duration_s, session.rest_duration_s]);

  // Auto-save the round plan ~600ms after the user stops adjusting,
  // so hitting Start Live Capture immediately picks up the latest
  // values without forcing a manual "Save plan" click. Only fires
  // while the session is still pending.
  const editable = session.status === "pending";
  const persisted = {
    rounds: session.round_count ?? 3,
    roundS: session.round_duration_s ?? 3,
    restS: session.rest_duration_s ?? 3,
  };
  useEffect(() => {
    if (!editable) return;
    if (
      rounds === persisted.rounds &&
      roundS === persisted.roundS &&
      restS === persisted.restS
    ) {
      return;
    }
    const t = setTimeout(() => {
      void save();
    }, 600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    rounds,
    roundS,
    restS,
    editable,
    persisted.rounds,
    persisted.roundS,
    persisted.restS,
  ]);

  const totalS =
    rounds * roundS + Math.max(0, rounds - 1) * restS; // no rest after last round
  const totalMin = totalS / 60;

  const save = async () => {
    setSaving(true);
    setErr(null);
    try {
      const updated = await api.patchSessionConfig(session.id, {
        round_count: rounds,
        round_duration_s: roundS,
        rest_duration_s: restS,
      });
      onChange(updated);
    } catch (e) {
      setErr(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-lg border border-neutral-800 bg-neutral-950/40 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">Round configuration</h2>
        <span className="text-xs text-neutral-500">
          plan = {rounds}×{fmtTime(roundS)} + {Math.max(0, rounds - 1)}×
          {fmtTime(restS)} rest = {fmtTime(totalS)} total
        </span>
      </div>
      {!editable && (
        <p className="mt-1 text-[11px] text-neutral-500">
          Locked once the session starts.
        </p>
      )}
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <NumberField
          label="Rounds"
          value={rounds}
          min={1}
          max={24}
          disabled={!editable || saving}
          onChange={setRounds}
        />
        <NumberField
          label="Round duration (s)"
          value={roundS}
          min={1}
          max={900}
          step={10}
          disabled={!editable || saving}
          onChange={setRoundS}
          hint={fmtTime(roundS)}
        />
        <NumberField
          label="Rest duration (s)"
          value={restS}
          min={0}
          max={600}
          step={10}
          disabled={!editable || saving}
          onChange={setRestS}
          hint={fmtTime(restS)}
        />
      </div>
      {editable && (
        <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
          <button
            onClick={save}
            disabled={saving}
            className="rounded-xl bg-emerald-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-emerald-400 disabled:bg-neutral-700"
          >
            {saving ? "Saving…" : "Save plan"}
          </button>
          <span className="text-neutral-500">
            Planned total: <strong>{totalMin.toFixed(1)} min</strong>
          </span>
          <PresetButton
            label="3×3 + 1 (pro)"
            onClick={() => {
              setRounds(3);
              setRoundS(180);
              setRestS(60);
            }}
          />
          <PresetButton
            label="12×3 + 1 (pro fight)"
            onClick={() => {
              setRounds(12);
              setRoundS(180);
              setRestS(60);
            }}
          />
          <PresetButton
            label="3×2 + 1 (amateur)"
            onClick={() => {
              setRounds(3);
              setRoundS(120);
              setRestS(60);
            }}
          />
        </div>
      )}
      {err && (
        <p className="mt-2 text-xs text-red-300">{err}</p>
      )}
    </section>
  );
}

function PresetButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-neutral-300 hover:bg-white/[0.07]"
    >
      {label}
    </button>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  disabled,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  disabled?: boolean;
  onChange: (v: number) => void;
  hint?: string;
}) {
  return (
    <div>
      <label className="text-xs text-neutral-400">{label}</label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
        className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-emerald-500/50 focus:outline-none disabled:opacity-50"
      />
      {hint && <div className="mt-1 text-[11px] text-neutral-500">{hint}</div>}
    </div>
  );
}

/**
 * Live round timer — shown during capturing/processing. Reads the planned
 * round structure from `session` and the elapsed time from `durationMs`
 * (which the capture runner exposes via the capture/status poll). Pure
 * arithmetic — no separate timer state to drift.
 */
export function RoundTimer({
  session,
  durationMs,
}: {
  session: Session;
  durationMs: number;
}) {
  const rounds = session.round_count ?? 3;
  const roundS = session.round_duration_s ?? 3;
  const restS = session.rest_duration_s ?? 3;
  const segmentS = roundS + restS;
  const elapsedS = durationMs / 1000;
  // Total session time (no rest after the last round)
  const totalS = rounds * roundS + Math.max(0, rounds - 1) * restS;
  const remainingS = Math.max(0, totalS - elapsedS);

  // Which segment are we in?
  let phase: "rest" | "round" | "done" = "round";
  let currentRound = 1;
  let timeInPhaseS = elapsedS;
  if (elapsedS >= totalS) {
    phase = "done";
    currentRound = rounds;
    timeInPhaseS = 0;
  } else {
    let acc = 0;
    for (let i = 1; i <= rounds; i++) {
      // round
      if (elapsedS < acc + roundS) {
        phase = "round";
        currentRound = i;
        timeInPhaseS = roundS - (elapsedS - acc);
        break;
      }
      acc += roundS;
      // rest after this round (no rest after the last)
      if (i < rounds && elapsedS < acc + restS) {
        phase = "rest";
        currentRound = i; // we just finished round i; resting before i+1
        timeInPhaseS = restS - (elapsedS - acc);
        break;
      }
      acc += restS;
    }
  }

  const phaseColor = {
    round: "text-emerald-300",
    rest: "text-amber-300",
    done: "text-violet-300",
  }[phase];
  const phaseBg = {
    round: "bg-emerald-500/5 border-emerald-500/30",
    rest: "bg-amber-500/5 border-amber-500/30",
    done: "bg-violet-500/5 border-violet-500/30",
  }[phase];

  return (
    <section className={`rounded-lg border p-4 ${phaseBg}`}>
      <div className="flex items-baseline justify-between">
        <h2 className={`text-base font-semibold ${phaseColor}`}>
          {phase === "done"
            ? "Session complete"
            : phase === "rest"
              ? `Rest after round ${currentRound}`
              : `Round ${currentRound} of ${rounds}`}
        </h2>
        <span className="text-xs text-neutral-500">
          plan: {rounds}×{fmtTime(roundS)} · rest {fmtTime(restS)}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <BigStat
          label={
            phase === "done" ? "Final" : phase === "rest" ? "Rest left" : "Round left"
          }
          value={fmtTime(timeInPhaseS)}
          tone={phase === "rest" ? "amber" : phase === "round" ? "emerald" : "violet"}
        />
        <BigStat
          label="Session elapsed"
          value={fmtTime(Math.min(elapsedS, totalS))}
        />
        <BigStat label="Session left" value={fmtTime(remainingS)} />
      </div>
      {/* Progress bar — total session */}
      <div className="mt-4">
        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-800">
          <div
            className={`h-2 ${
              phase === "rest" ? "bg-amber-500/70" : "bg-emerald-500/70"
            } transition-all`}
            style={{
              width: `${Math.min(100, (elapsedS / Math.max(totalS, 1)) * 100).toFixed(1)}%`,
            }}
          />
        </div>
      </div>
      {/* Per-round dots */}
      <div className="mt-3 flex flex-wrap gap-1">
        {Array.from({ length: rounds }, (_, i) => {
          const idx = i + 1;
          const status =
            idx < currentRound
              ? "done"
              : idx === currentRound
                ? phase === "rest"
                  ? "done" // round i is finished, in rest before i+1
                  : "active"
                : "pending";
          const tint =
            status === "done"
              ? "bg-emerald-500"
              : status === "active"
                ? "bg-emerald-300 animate-pulse"
                : "bg-neutral-700";
          return (
            <span
              key={idx}
              title={`Round ${idx}`}
              className={`h-2 w-8 rounded-full ${tint}`}
            />
          );
        })}
      </div>
    </section>
  );
}

function BigStat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "amber" | "emerald" | "violet";
}) {
  const color = {
    amber: "text-amber-200",
    emerald: "text-emerald-200",
    violet: "text-violet-200",
    undefined: "text-neutral-100",
  }[tone ?? ("undefined" as const)];
  return (
    <div className="rounded-xl border border-white/5 bg-black/20 p-3">
      <div className="text-[10px] uppercase tracking-wide text-neutral-500">
        {label}
      </div>
      <div className={`mt-1 font-mono text-3xl tabular-nums ${color}`}>
        {value}
      </div>
    </div>
  );
}

/**
 * Attachments card — generic file uploads (extra videos, sparring
 * photos, coach notes PDFs, etc.) hung off the session.
 */
export function AttachmentsCard({ sessionId }: { sessionId: string }) {
  const [items, setItems] = useState<SessionAttachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const refresh = async () => {
    try {
      setItems(await api.listAttachments(sessionId));
    } catch (e) {
      setErr(String(e));
    }
  };

  useEffect(() => {
    refresh();
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const onUpload = async (file: File) => {
    setBusy(true);
    setErr(null);
    try {
      await api.uploadAttachment(sessionId, file);
      await refresh();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (id: number) => {
    if (!confirm("Delete this attachment?")) return;
    try {
      await api.deleteAttachment(sessionId, id);
      await refresh();
    } catch (e) {
      setErr(String(e));
    }
  };

  const totalBytes = useMemo(
    () => items.reduce((s, a) => s + a.size_bytes, 0),
    [items],
  );

  return (
    <section className="rounded-lg border border-neutral-800 p-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-medium">Attachments</h2>
        <span className="text-xs text-neutral-500">
          {items.length} file{items.length === 1 ? "" : "s"} · {fmtBytes(totalBytes)}
        </span>
      </div>
      <p className="mt-1 text-[11px] text-neutral-500">
        Extra videos, sparring photos, coach notes — anything you want
        attached to this session for reference. Max 200 MB per file.
      </p>

      <div className="mt-3">
        <input
          type="file"
          disabled={busy}
          onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
          className="text-xs"
        />
        {busy && (
          <span className="ml-2 text-xs text-neutral-500">Uploading…</span>
        )}
      </div>

      {err && (
        <p className="mt-2 text-xs text-red-300">{err}</p>
      )}

      {items.length > 0 && (
        <ul className="mt-3 space-y-2">
          {items.map((a) => (
            <li
              key={a.id}
              className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 text-sm"
            >
              <span
                className="rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wide"
                style={{
                  backgroundColor: KIND_BG[a.kind],
                  color: KIND_FG[a.kind],
                }}
              >
                {a.kind}
              </span>
              <div className="min-w-0 flex-1">
                <div className="truncate font-medium">{a.filename}</div>
                <div className="text-xs text-neutral-500">
                  {fmtBytes(a.size_bytes)} ·{" "}
                  {new Date(a.uploaded_at).toLocaleString()}
                  {a.mime_type ? ` · ${a.mime_type}` : ""}
                </div>
              </div>
              <button
                onClick={() => onDelete(a.id)}
                className="text-xs text-neutral-500 hover:text-red-400"
              >
                remove
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

const KIND_BG: Record<AttachmentKind, string> = {
  video: "rgba(168, 85, 247, 0.15)",
  image: "rgba(56, 189, 248, 0.15)",
  audio: "rgba(34, 197, 94, 0.15)",
  document: "rgba(251, 146, 60, 0.15)",
  other: "rgba(148, 163, 184, 0.15)",
};
const KIND_FG: Record<AttachmentKind, string> = {
  video: "rgb(216, 180, 254)",
  image: "rgb(125, 211, 252)",
  audio: "rgb(134, 239, 172)",
  document: "rgb(253, 186, 116)",
  other: "rgb(203, 213, 225)",
};

/* ---------- helpers ---------- */

function fmtTime(seconds: number): string {
  const s = Math.max(0, Math.round(seconds));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

function fmtBytes(b: number): string {
  if (b < 1024) return `${b} B`;
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1024 * 1024 * 1024) return `${(b / 1024 / 1024).toFixed(1)} MB`;
  return `${(b / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

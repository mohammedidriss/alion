"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type Fighter, type SessionSource } from "@/lib/api";

// useSearchParams() forces client-side rendering at the prerender step,
// which Next 14 requires us to opt into via a Suspense boundary. The
// outer default export is the boundary; the inner function is the real
// page component that calls useSearchParams.
export default function NewSessionPage() {
  return (
    <Suspense
      fallback={<main className="p-8 text-sm text-neutral-400">Loading…</main>}
    >
      <NewSessionInner />
    </Suspense>
  );
}

function NewSessionInner() {
  const router = useRouter();
  const params = useSearchParams();
  const presetFighter = params.get("fighter");
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [fighterId, setFighterId] = useState<string>("");
  const [source, setSource] = useState<SessionSource>("live_webcam");
  const [newFighterName, setNewFighterName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // Round structure — set up before session creation so the fighter
  // doesn't have to configure mid-flow. Defaults match a typical pro
  // 3×3-minute round with 1-minute rest.
  const [rounds, setRounds] = useState<number>(3);
  const [roundS, setRoundS] = useState<number>(180);
  const [restS, setRestS] = useState<number>(60);

  useEffect(() => {
    api
      .listFighters()
      .then((fs) => {
        setFighters(fs);
        // Preselect the fighter from ?fighter=..., otherwise the first one.
        if (presetFighter && fs.some((f) => f.id === presetFighter)) {
          setFighterId(presetFighter);
        } else if (fs[0]) {
          setFighterId(fs[0].id);
        }
      })
      .catch((e) => setErr(String(e)));
  }, [presetFighter]);

  const createFighter = async () => {
    if (!newFighterName.trim()) return;
    const f = await api.createFighter(newFighterName.trim());
    setFighters([...fighters, f]);
    setFighterId(f.id);
    setNewFighterName("");
  };

  const submit = async () => {
    if (!fighterId) return;
    setBusy(true);
    setErr(null);
    try {
      const s = await api.createSession(fighterId, source);
      // Persist the round plan immediately so it's locked in before
      // the fighter hits "Start" on the detail page.
      await api.patchSessionConfig(s.id, {
        round_count: rounds,
        round_duration_s: roundS,
        rest_duration_s: restS,
      });
      router.push(`/sessions/${s.id}`);
    } catch (e) {
      setErr(String(e));
      setBusy(false);
    }
  };

  const totalS =
    rounds * roundS + Math.max(0, rounds - 1) * restS;
  const fmtTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  const fighter = fighters.find((x) => x.id === (presetFighter ?? fighterId));
  const fighterName = fighter?.name ?? "";

  return (
    <main className="mx-auto max-w-5xl space-y-6 p-8">
      {presetFighter && (
        <a
          href={`/fighters/${presetFighter}`}
          className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-200"
        >
          ← {fighterName || "Back to fighter"}
        </a>
      )}
      <h1 className="text-2xl font-semibold">
        New Session{fighterName && ` — ${fighterName}`}
      </h1>
      {err && <p className="text-sm text-red-400">{err}</p>}

      <section className="space-y-3 rounded-lg border border-neutral-800 p-4">
        <div className="flex items-baseline justify-between">
          <h2 className="text-sm font-medium text-neutral-300">Rounds</h2>
          <span className="text-xs text-neutral-500">
            plan = {rounds}×{fmtTime(roundS)}
            {rounds > 1 && ` + ${rounds - 1}×${fmtTime(restS)} rest`} ={" "}
            <strong className="text-neutral-300">{fmtTime(totalS)}</strong> total
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          <NumberField
            label="Number of rounds"
            value={rounds}
            min={1}
            max={24}
            onChange={setRounds}
          />
          <NumberField
            label="Round duration (s)"
            value={roundS}
            min={10}
            max={900}
            step={10}
            onChange={setRoundS}
            hint={fmtTime(roundS)}
          />
          <NumberField
            label="Rest duration (s)"
            value={restS}
            min={0}
            max={600}
            step={10}
            onChange={setRestS}
            hint={fmtTime(restS)}
          />
        </div>
        <div className="flex flex-wrap gap-2 pt-1 text-xs">
          <PresetChip
            label="3×3 + 1 (pro spar)"
            onClick={() => {
              setRounds(3);
              setRoundS(180);
              setRestS(60);
            }}
          />
          <PresetChip
            label="12×3 + 1 (pro fight)"
            onClick={() => {
              setRounds(12);
              setRoundS(180);
              setRestS(60);
            }}
          />
          <PresetChip
            label="3×2 + 1 (amateur)"
            onClick={() => {
              setRounds(3);
              setRoundS(120);
              setRestS(60);
            }}
          />
          <PresetChip
            label="6×3 + 1 (training)"
            onClick={() => {
              setRounds(6);
              setRoundS(180);
              setRestS(60);
            }}
          />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-6 md:grid-cols-[260px,1fr]">
        <section className="space-y-2 rounded-lg border border-neutral-800 p-4">
          <h2 className="text-sm font-medium text-neutral-300">Source</h2>
          <div className="flex flex-col gap-2">
            {(
              [
                ["live_webcam", "Live webcam"],
                ["uploaded_video", "Upload MP4"],
                ["hrv_replay", "HRV replay (RR CSV)"],
              ] as [SessionSource, string][]
            ).map(([s, label]) => (
              <label
                key={s}
                className={`cursor-pointer rounded border px-3 py-2 text-sm ${
                  source === s
                    ? "border-emerald-500 bg-emerald-900/20"
                    : "border-neutral-800"
                }`}
              >
                <input
                  type="radio"
                  className="hidden"
                  checked={source === s}
                  onChange={() => setSource(s)}
                />
                {label}
              </label>
            ))}
          </div>
        </section>

        <div className="space-y-4">
          {!presetFighter && (
            <section className="space-y-2 rounded-lg border border-neutral-800 p-4">
              <h2 className="text-sm font-medium text-neutral-300">Fighter</h2>
              {fighters.length > 0 ? (
                <select
                  className="w-full rounded bg-neutral-900 p-2 text-sm"
                  value={fighterId}
                  onChange={(e) => setFighterId(e.target.value)}
                >
                  {fighters.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name} ({f.stance})
                    </option>
                  ))}
                </select>
              ) : (
                <p className="text-sm text-neutral-500">No fighters yet.</p>
              )}
              <div className="mt-3 flex gap-2">
                <input
                  className="flex-1 rounded bg-neutral-900 p-2 text-sm"
                  placeholder="New fighter name…"
                  value={newFighterName}
                  onChange={(e) => setNewFighterName(e.target.value)}
                />
                <button
                  onClick={createFighter}
                  className="rounded bg-neutral-700 px-3 text-sm hover:bg-neutral-600"
                >
                  Add fighter
                </button>
              </div>
            </section>
          )}

          <button
            onClick={submit}
            disabled={!fighterId || busy}
            className="rounded bg-emerald-600 px-4 py-2 font-medium hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy ? "Starting…" : "Start session"}
          </button>
        </div>
      </div>
    </main>
  );
}

function NumberField({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  hint,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
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
        onChange={(e) => {
          const n = Number(e.target.value);
          if (Number.isFinite(n)) onChange(n);
        }}
        className="mt-1 w-full rounded bg-neutral-900 p-2 text-sm focus:outline-none focus:ring-1 focus:ring-emerald-500/40"
      />
      {hint && <div className="mt-1 text-[11px] text-neutral-500">{hint}</div>}
    </div>
  );
}

function PresetChip({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 text-xs text-neutral-300 hover:bg-white/[0.07]"
    >
      {label}
    </button>
  );
}

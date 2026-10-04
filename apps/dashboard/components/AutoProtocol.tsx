"use client";

/**
 * Automatic dataset protocol — hands-free recording of a take (ADR-013).
 *
 * Once the cameras roll it walks the protocol plan by itself: call the block and
 * count down → start the block at "go" → a beep cues every punch (the first one
 * second after go) → end the block two seconds after the last beep → rest →
 * next block. Timed blocks (no punches, free shadowboxing) run for their length.
 *
 * It drives the same protocol API as the manual Start/End buttons, so blocks, QA
 * counts and labels come out identical. Timing notes from the protocol side:
 * starting at "go" keeps fidgeting during the call-out out of the block, and the
 * last punch's IMU samples land ~1–1.3 s after its beep, so the block stays open
 * 2 s past the last one.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ProtocolBlockSpec, type TakeProtocol } from "@/lib/api";
import { beep, cueNow, hushCues, say, unlockCues } from "@/lib/cues";

const FIRST_BEEP_S = 1.0;
const END_AFTER_LAST_S = 2.0;
const COUNTDOWN = 3;
const PREFS_KEY = "alion.autoProtocol";

type Phase =
  | { kind: "waiting" }
  | { kind: "starting" } // run() called; keeps the poll from launching it twice
  | { kind: "countdown"; spec: ProtocolBlockSpec; n: number }
  | {
      kind: "block";
      spec: ProtocolBlockSpec;
      firstBeepWall: number; // wall ms of beep #1 (typed blocks)
      endWall: number;
      paceS: number;
    }
  | { kind: "rest"; next: ProtocolBlockSpec; untilWall: number }
  | { kind: "paused" }
  | { kind: "done" };

function loadPrefs(): { paceS: number; restS: number } {
  try {
    const p = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}");
    return {
      paceS: Number.isFinite(p.paceS) ? p.paceS : 1.5,
      restS: Number.isFinite(p.restS) ? p.restS : 20,
    };
  } catch {
    return { paceS: 1.5, restS: 20 };
  }
}

/** Plan blocks still to record, in order (latest kept attempt not finished). */
function remaining(p: TakeProtocol, skipped: Set<string>): ProtocolBlockSpec[] {
  const latest = new Map<string, { t_end_ms: number | null }>();
  for (const b of p.blocks) if (!b.discarded) latest.set(b.key, b);
  return p.plan.filter((s) => latest.get(s.key)?.t_end_ms == null && !skipped.has(s.key));
}

function describe(spec: ProtocolBlockSpec): string {
  if (spec.reps) return `${spec.reps} punches`;
  if (spec.duration_s) return `${Math.round(spec.duration_s / 60)} minutes`;
  return "";
}

function mmss(ms: number): string {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function AutoProtocol({ takeId }: { takeId: string }) {
  const [proto, setProto] = useState<TakeProtocol | null>(null);
  const [phase, setPhaseState] = useState<Phase>({ kind: "waiting" });
  const [prefs, setPrefs] = useState(() => ({ paceS: 1.5, restS: 20 }));
  const [err, setErr] = useState<string | null>(null);
  const [, setTick] = useState(0);

  const phaseRef = useRef<Phase>({ kind: "waiting" });
  const gen = useRef(0); // bumped to cancel a running sequence
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const skipped = useRef(new Set<string>());
  const current = useRef<{ key: string; index: number } | null>(null); // open attempt
  const lastDone = useRef<{ key: string; index: number } | null>(null);
  const prefsRef = useRef(prefs);
  prefsRef.current = prefs;

  const setPhase = (p: Phase) => {
    phaseRef.current = p;
    setPhaseState(p);
  };

  useEffect(() => setPrefs(loadPrefs()), []);
  useEffect(() => {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch {
      /* private mode — prefs just don't persist */
    }
  }, [prefs]);

  // Sound needs a user gesture: the coach's click on "Start all cameras" unlocks it.
  useEffect(() => {
    const unlock = () => unlockCues();
    document.addEventListener("pointerdown", unlock, { once: true });
    return () => document.removeEventListener("pointerdown", unlock);
  }, []);

  const wait = (ms: number) =>
    new Promise<void>((resolve) => {
      const id = setTimeout(() => {
        timers.current.delete(id);
        resolve();
      }, Math.max(0, ms));
      timers.current.add(id);
    });

  const cancel = useCallback(() => {
    gen.current += 1;
    for (const id of timers.current) clearTimeout(id);
    timers.current.clear();
    hushCues();
  }, []);

  useEffect(() => () => cancel(), [cancel]);

  /** Run the sequence from the next remaining block (or `startKey`). */
  const run = useCallback(
    async (startKey?: string) => {
      cancel();
      const my = gen.current;
      const alive = () => gen.current === my;
      setErr(null);
      setPhase({ kind: "starting" });
      let first = true;
      let forceKey = startKey;
      while (alive()) {
        const p = await api.protocol(takeId).catch(() => null);
        if (!alive()) return;
        if (!p) {
          setErr("Lost contact with the server — automation stopped.");
          setPhase({ kind: "paused" });
          return;
        }
        setProto(p);
        if (!p.recording) {
          setPhase({ kind: "waiting" });
          return;
        }
        if (p.active != null) {
          await api.protocolEnd(takeId).catch(() => null); // close a stray open block
          continue;
        }
        const todo = remaining(p, skipped.current);
        const spec = (forceKey && p.plan.find((s) => s.key === forceKey)) || todo[0];
        forceKey = undefined;
        if (!spec) {
          say("Protocol complete. Press stop and save.");
          setPhase({ kind: "done" });
          return;
        }

        // Rest between blocks (not before the first block of a run).
        const { paceS, restS } = prefsRef.current;
        if (!first && restS > 0) {
          setPhase({ kind: "rest", next: spec, untilWall: Date.now() + restS * 1000 });
          say(`Rest. Next, ${spec.title}.`);
          await wait(restS * 1000);
          if (!alive()) return;
        }
        first = false;

        // Call the block, then 3-2-1.
        setPhase({ kind: "countdown", spec, n: COUNTDOWN });
        say(`${spec.title}. ${describe(spec)}.`);
        await wait(2200);
        for (let n = COUNTDOWN; n >= 1; n--) {
          if (!alive()) return;
          setPhase({ kind: "countdown", spec, n });
          beep({ freq: 660, ms: 120 });
          await wait(1000);
        }
        if (!alive()) return;

        // Go: the block starts now, so the call-out stays outside it.
        beep({ freq: 1320, ms: 260 });
        let started: TakeProtocol;
        try {
          started = await api.protocolStart(takeId, spec.key);
        } catch (e) {
          setErr(`Couldn't start ${spec.title}: ${String(e).slice(0, 120)}`);
          setPhase({ kind: "paused" });
          return;
        }
        if (!alive()) return;
        setProto(started);
        const open = started.active != null ? started.blocks[started.active] : null;
        current.current = open ? { key: spec.key, index: open.index } : null;

        const now = Date.now();
        let blockMs: number;
        if (spec.reps) {
          const base = cueNow() + FIRST_BEEP_S;
          for (let i = 0; i < spec.reps; i++) beep({ at: base + i * paceS, freq: 990, ms: 80 });
          blockMs = (FIRST_BEEP_S + (spec.reps - 1) * paceS + END_AFTER_LAST_S) * 1000;
        } else {
          say("Go.");
          const dur = spec.duration_s ?? 60;
          if (dur > 12) beep({ at: cueNow() + dur - 10, freq: 990, ms: 200 }); // 10 s left
          blockMs = dur * 1000;
        }
        setPhase({
          kind: "block",
          spec,
          firstBeepWall: now + FIRST_BEEP_S * 1000,
          endWall: now + blockMs,
          paceS,
        });
        await wait(blockMs);
        if (!alive()) return;

        const ended = await api.protocolEnd(takeId).catch(() => null);
        if (!alive()) return;
        if (ended) setProto(ended);
        beep({ freq: 440, ms: 350 });
        lastDone.current = current.current;
        current.current = null;
      }
    },
    [takeId, cancel],
  );

  // Poll the protocol: start the sequence when the cameras roll; stop it if they stop.
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      const p = await api.protocol(takeId).catch(() => null);
      if (!alive || !p) return;
      setProto(p);
      const kind = phaseRef.current.kind;
      if (p.recording && kind === "waiting" && p.active == null) {
        void run();
      } else if (!p.recording && (kind === "countdown" || kind === "block" || kind === "rest")) {
        cancel();
        setPhase({ kind: "waiting" });
      }
    };
    poll();
    const id = setInterval(poll, 1000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [takeId, run, cancel]);

  // Redraw the counters ~5×/s while something is running.
  useEffect(() => {
    if (!["countdown", "block", "rest"].includes(phase.kind)) return;
    const id = setInterval(() => setTick((t) => t + 1), 200);
    return () => clearInterval(id);
  }, [phase.kind]);

  const endAndDiscard = async (attempt: { key: string; index: number } | null) => {
    if (!attempt) return;
    await api.protocolEnd(takeId).catch(() => null);
    await api.protocolDiscard(takeId, attempt.index).catch(() => null);
  };

  const skip = async () => {
    unlockCues();
    const ph = phaseRef.current;
    cancel();
    if (ph.kind === "block") await endAndDiscard(current.current);
    current.current = null;
    const key =
      ph.kind === "block" || ph.kind === "countdown" ? ph.spec.key : ph.kind === "rest" ? ph.next.key : null;
    if (key) skipped.current.add(key);
    void run();
  };

  const redo = async () => {
    unlockCues();
    const ph = phaseRef.current;
    cancel();
    if (ph.kind === "block") {
      await endAndDiscard(current.current);
      current.current = null;
      void run(ph.spec.key);
    } else if (ph.kind === "rest" && lastDone.current) {
      const prev = lastDone.current;
      await api.protocolDiscard(takeId, prev.index).catch(() => null);
      lastDone.current = null;
      void run(prev.key);
    } else if (ph.kind === "countdown") {
      void run(ph.spec.key);
    }
  };

  const stop = async () => {
    const ph = phaseRef.current;
    cancel();
    if (ph.kind === "block") {
      await api.protocolEnd(takeId).catch(() => null); // keep what was recorded
      lastDone.current = current.current;
      current.current = null;
    }
    setPhase({ kind: "paused" });
  };

  const resume = () => {
    unlockCues();
    skipped.current.clear();
    void run();
  };

  // ---------------------------------------------------------------------------

  const total = proto?.plan.length ?? 0;
  const left = proto ? remaining(proto, new Set()).length : 0;
  const running = phase.kind === "countdown" || phase.kind === "block" || phase.kind === "rest";
  const now = Date.now();

  let big: React.ReactNode = null;
  if (phase.kind === "countdown") {
    big = (
      <Display title={phase.spec.title} sub={describe(phase.spec)}>
        <span className="text-6xl font-bold tabular-nums text-amber-300">{phase.n}</span>
      </Display>
    );
  } else if (phase.kind === "block") {
    const { spec } = phase;
    if (spec.reps) {
      const n = Math.min(
        spec.reps,
        Math.max(0, Math.floor((now - phase.firstBeepWall) / (phase.paceS * 1000)) + 1),
      );
      big = (
        <Display title={spec.title} sub={spec.hint || "Punch on each beep"} live>
          <span className="text-6xl font-bold tabular-nums">
            {n}
            <span className="text-2xl text-neutral-500"> / {spec.reps}</span>
          </span>
          <Progress frac={n / spec.reps} />
        </Display>
      );
    } else {
      const dur = (spec.duration_s ?? 60) * 1000;
      const leftMs = phase.endWall - now;
      big = (
        <Display title={spec.title} sub={spec.hint} live>
          <span className="text-6xl font-bold tabular-nums">{mmss(leftMs)}</span>
          <Progress frac={1 - leftMs / dur} />
        </Display>
      );
    }
  } else if (phase.kind === "rest") {
    big = (
      <Display title="Rest" sub={`Next: ${phase.next.title} · ${describe(phase.next)}`}>
        <span className="text-6xl font-bold tabular-nums text-sky-300">
          {mmss(phase.untilWall - now)}
        </span>
      </Display>
    );
  } else if (phase.kind === "done") {
    big = (
      <Display title="Protocol complete" sub="Wait a second, then press Stop & save.">
        <span className="text-4xl">✓</span>
      </Display>
    );
  }

  return (
    <div className="rounded-2xl border border-white/10 p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">Automatic protocol</span>
        <span className="text-[11px] text-neutral-500">
          {total ? `${total - left}/${total} blocks` : ""}
        </span>
      </div>

      {phase.kind === "waiting" && (
        <p className="mt-2 text-xs text-neutral-400">
          Press <strong className="text-neutral-200">Start all cameras</strong> — the protocol then
          runs itself: a voice calls each block, a beep cues every punch, and it rests and moves on.
        </p>
      )}
      {phase.kind === "paused" && (
        <p className="mt-2 text-xs text-neutral-400">
          Automation stopped. Resume continues with the next unrecorded block.
        </p>
      )}

      {big && <div className="mt-3">{big}</div>}

      <div className="mt-3 flex flex-wrap gap-2">
        {running && (
          <>
            <button
              onClick={redo}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
              title="Throw this block again (the attempt is discarded)"
            >
              ↺ Redo
            </button>
            <button
              onClick={skip}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-xs hover:bg-white/5"
              title="Leave this block out for now"
            >
              Skip ⏭
            </button>
            <button
              onClick={stop}
              className="rounded-lg border border-red-500/40 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10"
            >
              ■ Stop automation
            </button>
          </>
        )}
        {(phase.kind === "paused" || phase.kind === "done") && proto?.recording && left > 0 && (
          <button
            onClick={resume}
            className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-black hover:bg-emerald-400"
          >
            ▶ Resume
          </button>
        )}
      </div>

      {!running && (
        <div className="mt-3 flex flex-wrap gap-4 border-t border-white/5 pt-3 text-xs text-neutral-400">
          <label className="flex items-center gap-2">
            Pace
            <input
              type="number"
              min={0.5}
              max={4}
              step={0.1}
              value={prefs.paceS}
              onChange={(e) =>
                setPrefs((p) => ({ ...p, paceS: Math.min(4, Math.max(0.5, Number(e.target.value) || 1.5)) }))
              }
              className="w-16 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-neutral-200"
            />
            s / punch
          </label>
          <label className="flex items-center gap-2">
            Rest
            <input
              type="number"
              min={0}
              max={180}
              step={5}
              value={prefs.restS}
              onChange={(e) =>
                setPrefs((p) => ({ ...p, restS: Math.min(180, Math.max(0, Number(e.target.value) || 0)) }))
              }
              className="w-16 rounded-md border border-white/10 bg-black/30 px-2 py-1 text-neutral-200"
            />
            s
          </label>
        </div>
      )}
      {err && <p className="mt-2 text-xs text-red-300">{err}</p>}
    </div>
  );
}

function Display({
  title,
  sub,
  live = false,
  children,
}: {
  title: string;
  sub?: string;
  live?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-black/40 p-4 text-center">
      <div className="flex items-center justify-center gap-2 text-lg font-semibold uppercase tracking-wide">
        {live && <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-red-500" />}
        {title}
      </div>
      {sub && <div className="mt-0.5 text-xs text-neutral-400">{sub}</div>}
      <div className="mt-2">{children}</div>
    </div>
  );
}

function Progress({ frac }: { frac: number }) {
  return (
    <div className="mx-auto mt-3 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
      <div
        className="h-full rounded-full bg-emerald-400 transition-[width] duration-200"
        style={{ width: `${Math.min(100, Math.max(0, frac * 100))}%` }}
      />
    </div>
  );
}

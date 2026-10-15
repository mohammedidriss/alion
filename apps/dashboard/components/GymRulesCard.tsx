"use client";

/**
 * The gym's rules (ADR-055): fighters accept them when they join, and again when
 * they change — the gym's Members page shows who hasn't yet.
 */

import { useEffect, useState } from "react";
import { api, type Gym } from "@/lib/api";

export function GymRulesCard({ gym, onSaved }: { gym: Gym; onSaved?: (g: Gym) => void }) {
  const [text, setText] = useState(gym.rules ?? "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => setText(gym.rules ?? ""), [gym.rules]);

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const g = await api.updateGym(gym.id, { rules: text });
      setMsg(g.rules ? `Saved — version ${g.rules_version}. Members are asked to accept them.` : "Saved: no rules.");
      onSaved?.(g);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card space-y-2">
      <h2 className="text-base font-semibold">Gym rules</h2>
      <p className="text-xs text-neutral-500">
        Fighters accept these when they join, and again whenever you change them.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="e.g. Gloves and wraps on in the ring. No sparring without a coach."
        className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
      />
      <div className="flex items-center gap-3">
        <button
          onClick={() => void save()}
          disabled={busy || text === (gym.rules ?? "")}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          Save rules
        </button>
        {msg && <span className="text-xs text-neutral-400">{msg}</span>}
      </div>
    </section>
  );
}

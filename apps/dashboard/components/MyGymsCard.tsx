"use client";

/**
 * The gyms the signed-in fighter is in, and leaving one (ADR-050): its managers stop
 * seeing their training, and the gym's coaches stop coaching them through it.
 * Shows nothing when they're in no gym.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type MyGym } from "@/lib/api";

export function MyGymsCard({ onChanged }: { onChanged?: () => void }) {
  const [gyms, setGyms] = useState<MyGym[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .myGyms()
      .then(setGyms)
      .catch(() => setGyms([]));
  }, []);
  useEffect(() => load(), [load]);

  const leave = async (g: MyGym) => {
    const ok = confirm(
      `Leave ${g.gym_name}? Its managers stop seeing your training, and its coaches stop coaching you ` +
        `through the gym. Your sessions stay yours. To come back, the gym invites you again.`,
    );
    if (!ok) return;
    setBusy(g.id);
    setErr(null);
    try {
      await api.leaveGym(g.id);
      load();
      onChanged?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (gyms.length === 0) return null;
  return (
    <div className="card space-y-3">
      <h2 className="text-base font-semibold">{gyms.length === 1 ? "Your gym" : "Your gyms"}</h2>
      {err && <p className="text-sm text-red-300">{err}</p>}
      {gyms.map((g) => (
        <div key={g.id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-white/10 p-3 text-sm">
          <div>
            <b className="text-neutral-100">{g.gym_name}</b>
            {g.gym_city && <span className="text-neutral-400"> · {g.gym_city}</span>}
            <div className="text-xs text-neutral-500">
              {g.status}
              {g.joined_on && ` since ${new Date(g.joined_on).toLocaleDateString()}`}
            </div>
          </div>
          <button
            onClick={() => void leave(g)}
            disabled={busy !== null}
            className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-40"
          >
            {busy === g.id ? "Leaving…" : "Leave"}
          </button>
        </div>
      ))}
    </div>
  );
}

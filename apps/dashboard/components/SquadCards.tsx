"use client";

/**
 * Squads where people look for them (ADR-053): a fighter's squads on their Team
 * page (they can make one their main squad, or leave one), a coach's squads with
 * their fighters, and the gym's squads this week on its dashboard.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Squad } from "@/lib/api";

const KIND: Record<string, string> = { competition: "competition team", class: "class", camp: "fight camp", other: "squad" };

export function FighterSquadsCard({ fighterId, own }: { fighterId: string; own: boolean }) {
  const [squads, setSquads] = useState<Squad[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => {
    api.fighterSquads(fighterId).then(setSquads).catch(() => setSquads([]));
  }, [fighterId]);
  useEffect(() => load(), [load]);

  const act = async (fn: () => Promise<unknown>) => {
    setErr(null);
    try {
      await fn();
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  if (squads.length === 0) return null;
  return (
    <section className="card space-y-2">
      <h2 className="text-base font-semibold">Squads</h2>
      {err && <p className="text-sm text-red-300">{err}</p>}
      <ul className="divide-y divide-white/5 text-sm">
        {squads.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div>
              <span className="font-medium text-neutral-100">{s.name}</span>
              <span className="ml-2 text-xs text-neutral-500">
                {KIND[s.kind]} at {s.gym_name}
                {s.coaches.length > 0 && ` · ${s.coaches.join(", ")}`}
              </span>
              {s.is_main && <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">main squad</span>}
            </div>
            {own && s.member_id != null && (
              <span className="flex gap-1">
                {!s.is_main && (
                  <button onClick={() => void act(() => api.setMainSquad(s.id, s.member_id as number, true))} className="rounded-lg px-2 py-1 text-xs text-neutral-400 hover:bg-white/5">
                    Make main
                  </button>
                )}
                <button
                  onClick={() => {
                    if (confirm(`Leave ${s.name}? Its coaches stop seeing your training through it.`))
                      void act(() => api.endSquadMember(s.id, s.member_id as number));
                  }}
                  className="rounded-lg px-2 py-1 text-xs text-red-400/70 hover:bg-red-500/10"
                >
                  Leave
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      <p className="text-xs text-neutral-500">
        A session is trained with your main squad unless another is chosen; the squad&apos;s coaches see your training while you&apos;re both on it.
      </p>
    </section>
  );
}

export function MySquadsCard() {
  const [squads, setSquads] = useState<Squad[]>([]);
  useEffect(() => {
    api.mySquads().then(setSquads).catch(() => setSquads([]));
  }, []);
  if (squads.length === 0) return null;
  return (
    <section className="card space-y-3">
      <h2 className="text-base font-semibold">My squads</h2>
      {squads.map((s) => (
        <div key={s.id}>
          <div className="text-sm">
            <span className="font-medium text-neutral-100">{s.name}</span>
            <span className="ml-2 text-xs text-neutral-500">{KIND[s.kind]} at {s.gym_name}</span>
          </div>
          <div className="mt-1 flex flex-wrap gap-1.5">
            {(s.members ?? []).map((m) => (
              <Link key={m.id} href={`/fighters/${m.fighter_id}`} className="rounded-full bg-white/[0.05] px-2.5 py-1 text-xs text-neutral-200 hover:bg-white/[0.1]">
                {m.name}
              </Link>
            ))}
            {(s.members ?? []).length === 0 && <span className="text-xs text-neutral-500">No fighters yet.</span>}
          </div>
        </div>
      ))}
    </section>
  );
}

export function GymSquadsWeekCard({ gymId }: { gymId: string }) {
  const [squads, setSquads] = useState<Squad[]>([]);
  useEffect(() => {
    api.gymSquads(gymId).then(setSquads).catch(() => setSquads([]));
  }, [gymId]);
  if (squads.length === 0) return null;
  return (
    <section className="card space-y-2">
      <div className="flex items-baseline justify-between">
        <h2 className="text-base font-semibold">Squads this week</h2>
        <Link href="/squads" className="text-xs text-emerald-400 hover:underline">Manage squads</Link>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] text-sm">
          <thead className="text-left text-xs text-neutral-500">
            <tr>
              <th className="py-1.5 pr-3 font-medium">Squad</th>
              <th className="py-1.5 pr-3 font-medium">Trained</th>
              <th className="py-1.5 font-medium">Sessions with the squad</th>
            </tr>
          </thead>
          <tbody>
            {squads.filter((s) => s.open).map((s) => (
              <tr key={s.id} className="border-t border-white/5">
                <td className="py-1.5 pr-3">{s.name}</td>
                <td className={`py-1.5 pr-3 ${s.trained_7d !== null && s.trained_7d < s.fighters ? "text-amber-300" : ""}`}>
                  {s.trained_7d ?? "—"} of {s.fighters}
                </td>
                <td className="py-1.5">{s.sessions_7d ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

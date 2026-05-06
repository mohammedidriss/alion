"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Fighter, type Session, type Stance } from "@/lib/api";

interface FighterRow {
  fighter: Fighter;
  sessionCount: number;
  lastSessionAt: string | null;
  lastSession: Session | null;
}

export default function Home() {
  const [health, setHealth] = useState<{ status: string; schema_version: string } | null>(
    null,
  );
  const [rows, setRows] = useState<FighterRow[]>([]);
  const [allSessions, setAllSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newStance, setNewStance] = useState<Stance>("orthodox");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    try {
      const [hRes, fighters, sessions] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        api.listFighters(),
        api.listSessions(),
      ]);
      setHealth(hRes);
      setAllSessions(sessions);
      const byFighter = new Map<string, Session[]>();
      for (const s of sessions) {
        const arr = byFighter.get(s.fighter_id) ?? [];
        arr.push(s);
        byFighter.set(s.fighter_id, arr);
      }
      const out: FighterRow[] = fighters.map((f) => {
        const ss = (byFighter.get(f.id) ?? [])
          .slice()
          .sort((a, b) => b.started_at.localeCompare(a.started_at));
        return {
          fighter: f,
          sessionCount: ss.length,
          lastSessionAt: ss[0]?.started_at ?? null,
          lastSession: ss[0] ?? null,
        };
      });
      out.sort((a, b) => (b.lastSessionAt ?? "").localeCompare(a.lastSessionAt ?? ""));
      setRows(out);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addFighter = async () => {
    if (!newName.trim()) return;
    setAdding(true);
    try {
      await api.createFighter(newName.trim(), newStance);
      setNewName("");
      await load();
    } catch (e) {
      setErr(String(e));
    } finally {
      setAdding(false);
    }
  };

  const recentSessions = [...allSessions]
    .sort((a, b) => b.started_at.localeCompare(a.started_at))
    .slice(0, 6);
  const fighterById = new Map(rows.map((r) => [r.fighter.id, r.fighter]));

  return (
    <div className="mx-auto max-w-7xl space-y-6 px-8 py-8">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">Roster</h1>
          <p className="mt-1 text-sm text-neutral-400">
            Pick a fighter to open their dashboard.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {health ? (
            <span className="pill bg-emerald-500/15 text-emerald-300">
              ● API healthy · schema {health.schema_version}
            </span>
          ) : (
            <span className="pill bg-amber-500/15 text-amber-300">● API unreachable</span>
          )}
        </div>
      </header>

      {err && (
        <p className="rounded-2xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">
          {err}
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base font-semibold">Fighters</h2>
            <span className="text-xs text-neutral-500">{rows.length} total</span>
          </div>
          {rows.length === 0 ? (
            <p className="mt-4 text-sm text-neutral-500">
              No fighters yet — add one to get started.
            </p>
          ) : (
            <ul className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {rows.map((r) => (
                <li key={r.fighter.id}>
                  <Link
                    href={`/fighters/${r.fighter.id}`}
                    className="group flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-colors hover:border-white/15 hover:bg-white/[0.05]"
                  >
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-violet-500/30 to-emerald-400/30 text-sm font-semibold">
                      {r.fighter.name.charAt(0).toUpperCase()}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{r.fighter.name}</div>
                      <div className="text-xs text-neutral-500">
                        {r.fighter.stance} ·{" "}
                        {r.sessionCount} session{r.sessionCount === 1 ? "" : "s"}
                      </div>
                    </div>
                    <span className="text-neutral-600 group-hover:text-neutral-300">
                      ›
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-5 border-t border-white/5 pt-4">
            <h3 className="text-sm font-medium text-neutral-300">Add a fighter</h3>
            <div className="mt-2 flex flex-wrap gap-2">
              <input
                className="flex-1 rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-violet-500/50 focus:outline-none"
                placeholder="Name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addFighter()}
              />
              <select
                className="rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-violet-500/50 focus:outline-none"
                value={newStance}
                onChange={(e) => setNewStance(e.target.value as Stance)}
              >
                <option value="orthodox">orthodox</option>
                <option value="southpaw">southpaw</option>
                <option value="switch">switch</option>
              </select>
              <button
                onClick={addFighter}
                disabled={!newName.trim() || adding}
                className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-neutral-800 disabled:text-neutral-500"
              >
                {adding ? "Adding…" : "Add"}
              </button>
            </div>
          </div>
        </section>

        <section className="card">
          <div className="flex items-baseline justify-between">
            <h2 className="text-base font-semibold">Recent sessions</h2>
            <span className="text-xs text-neutral-500">{recentSessions.length}</span>
          </div>
          {recentSessions.length === 0 ? (
            <p className="mt-4 text-sm text-neutral-500">No sessions yet.</p>
          ) : (
            <ul className="mt-4 space-y-2">
              {recentSessions.map((s) => {
                const f = fighterById.get(s.fighter_id);
                const tint =
                  s.status === "completed"
                    ? "bg-emerald-500/15 text-emerald-300"
                    : s.status === "failed"
                      ? "bg-red-500/15 text-red-300"
                      : s.status === "capturing" || s.status === "processing"
                        ? "bg-amber-500/15 text-amber-300"
                        : "bg-neutral-700/40 text-neutral-300";
                return (
                  <li key={s.id}>
                    <Link
                      href={`/sessions/${s.id}`}
                      className="block rounded-xl border border-white/5 bg-white/[0.02] p-3 transition-colors hover:border-white/15 hover:bg-white/[0.05]"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-sm font-medium">
                          {f?.name ?? "—"}
                        </span>
                        <span className={`pill ${tint}`}>{s.status}</span>
                      </div>
                      <div className="mt-1 flex items-center justify-between text-xs text-neutral-500">
                        <span>{s.source.replace(/_/g, " ")}</span>
                        <span>{new Date(s.started_at).toLocaleString()}</span>
                      </div>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}


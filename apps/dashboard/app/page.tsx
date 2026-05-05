"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Fighter, type Session, type Stance } from "@/lib/api";

interface FighterRow {
  fighter: Fighter;
  sessionCount: number;
  lastSessionAt: string | null;
}

export default function Home() {
  const [health, setHealth] = useState<{ status: string; schema_version: string } | null>(
    null,
  );
  const [rows, setRows] = useState<FighterRow[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [newStance, setNewStance] = useState<Stance>("orthodox");

  const load = useCallback(async () => {
    try {
      const [hRes, fighters, allSessions] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        api.listFighters(),
        api.listSessions(),
      ]);
      setHealth(hRes);
      const byFighter = new Map<string, Session[]>();
      for (const s of allSessions) {
        const arr = byFighter.get(s.fighter_id) ?? [];
        arr.push(s);
        byFighter.set(s.fighter_id, arr);
      }
      const out: FighterRow[] = fighters.map((f) => {
        const ss = (byFighter.get(f.id) ?? []).slice().sort((a, b) =>
          b.started_at.localeCompare(a.started_at),
        );
        return {
          fighter: f,
          sessionCount: ss.length,
          lastSessionAt: ss[0]?.started_at ?? null,
        };
      });
      out.sort((a, b) =>
        (b.lastSessionAt ?? "").localeCompare(a.lastSessionAt ?? ""),
      );
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
    try {
      await api.createFighter(newName.trim(), newStance);
      setNewName("");
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <main className="mx-auto max-w-3xl space-y-8 p-8">
      <header>
        <h1 className="text-3xl font-semibold">Alion</h1>
        <p className="mt-1 text-neutral-400">Phase 1 — single-stream CV capture.</p>
      </header>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">API</h2>
        {health ? (
          <p className="mt-1 text-sm text-emerald-400">
            ✓ healthy · schema {health.schema_version}
          </p>
        ) : (
          <p className="mt-1 text-sm text-amber-400">
            API unreachable — start with{" "}
            <code className="text-amber-200">uv run uvicorn api.main:app --reload</code>.
          </p>
        )}
      </section>

      {err && (
        <p className="rounded border border-red-700/60 bg-red-950/40 p-3 text-sm text-red-300">
          {err}
        </p>
      )}

      <section className="rounded-lg border border-neutral-800 p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">Fighters ({rows.length})</h2>
        </div>

        {rows.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">
            No fighters yet — add one below to get started.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-neutral-800">
            {rows.map((r) => (
              <li key={r.fighter.id}>
                <Link
                  href={`/fighters/${r.fighter.id}`}
                  className="block rounded px-2 py-3 text-sm hover:bg-neutral-900"
                >
                  <div className="flex items-baseline justify-between">
                    <span className="text-base font-medium">{r.fighter.name}</span>
                    <span className="text-xs text-neutral-500">
                      {r.fighter.stance}
                    </span>
                  </div>
                  <div className="mt-1 flex justify-between text-xs text-neutral-500">
                    <span>
                      {r.sessionCount} session{r.sessionCount === 1 ? "" : "s"}
                    </span>
                    <span>
                      {r.lastSessionAt
                        ? `last: ${new Date(r.lastSessionAt).toLocaleString()}`
                        : "no sessions yet"}
                    </span>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-4 border-t border-neutral-800 pt-4">
          <h3 className="text-sm font-medium text-neutral-300">Add a fighter</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            <input
              className="flex-1 rounded bg-neutral-900 p-2 text-sm"
              placeholder="Name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && addFighter()}
            />
            <select
              className="rounded bg-neutral-900 p-2 text-sm"
              value={newStance}
              onChange={(e) => setNewStance(e.target.value as Stance)}
            >
              <option value="orthodox">orthodox</option>
              <option value="southpaw">southpaw</option>
              <option value="switch">switch</option>
            </select>
            <button
              onClick={addFighter}
              className="rounded bg-emerald-600 px-3 py-2 text-sm font-medium hover:bg-emerald-500"
            >
              Add
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}

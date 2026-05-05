"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, type Fighter, type Session, type Stance } from "@/lib/api";

const ACTIVE_FIGHTER_KEY = "alion.activeFighterId";
const ALL = "__all__";

export default function Home() {
  const [health, setHealth] = useState<{ status: string; schema_version: string } | null>(null);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [activeFighter, setActiveFighter] = useState<string>(ALL);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editStance, setEditStance] = useState<Stance>("orthodox");
  const [confirmDeleteFighter, setConfirmDeleteFighter] = useState<string | null>(null);
  const [confirmDeleteSession, setConfirmDeleteSession] = useState<string | null>(null);

  const loadHealth = useCallback(async () => {
    try {
      const r = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { cache: "no-store" });
      if (r.ok) setHealth(await r.json());
    } catch {
      setHealth(null);
    }
  }, []);

  const loadFighters = useCallback(async () => {
    try {
      setFighters(await api.listFighters());
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  const loadSessions = useCallback(async (fighterId: string) => {
    try {
      setSessions(await api.listSessions(fighterId === ALL ? undefined : fighterId));
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(ACTIVE_FIGHTER_KEY);
    if (stored) setActiveFighter(stored);
    loadHealth();
    loadFighters();
  }, [loadHealth, loadFighters]);

  useEffect(() => {
    localStorage.setItem(ACTIVE_FIGHTER_KEY, activeFighter);
    loadSessions(activeFighter);
  }, [activeFighter, loadSessions]);

  const startEdit = (f: Fighter) => {
    setEditingId(f.id);
    setEditName(f.name);
    setEditStance(f.stance);
  };

  const saveEdit = async (id: string) => {
    try {
      await api.updateFighter(id, { name: editName.trim(), stance: editStance });
      setEditingId(null);
      await loadFighters();
    } catch (e) {
      setErr(String(e));
    }
  };

  const doDeleteFighter = async (id: string) => {
    try {
      await api.deleteFighter(id);
      setConfirmDeleteFighter(null);
      if (activeFighter === id) setActiveFighter(ALL);
      await Promise.all([loadFighters(), loadSessions(activeFighter === id ? ALL : activeFighter)]);
    } catch (e) {
      setErr(String(e));
    }
  };

  const doDeleteSession = async (id: string) => {
    try {
      await api.deleteSession(id);
      setConfirmDeleteSession(null);
      await loadSessions(activeFighter);
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
          <h2 className="font-medium">Active fighter</h2>
        </div>
        {fighters.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">
            No fighters yet — start with{" "}
            <Link href="/sessions/new" className="underline">
              New session
            </Link>{" "}
            to create one.
          </p>
        ) : (
          <select
            className="mt-3 w-full rounded bg-neutral-900 p-2 text-sm"
            value={activeFighter}
            onChange={(e) => setActiveFighter(e.target.value)}
          >
            <option value={ALL}>All fighters</option>
            {fighters.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name} ({f.stance})
              </option>
            ))}
          </select>
        )}

        {fighters.length > 0 && (
          <ul className="mt-3 divide-y divide-neutral-800">
            {fighters.map((f) => (
              <li key={f.id} className="py-2 text-sm">
                {editingId === f.id ? (
                  <div className="flex items-center gap-2">
                    <input
                      className="flex-1 rounded bg-neutral-900 px-2 py-1 text-sm"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                    />
                    <select
                      className="rounded bg-neutral-900 px-2 py-1 text-xs"
                      value={editStance}
                      onChange={(e) => setEditStance(e.target.value as Stance)}
                    >
                      <option value="orthodox">orthodox</option>
                      <option value="southpaw">southpaw</option>
                      <option value="switch">switch</option>
                    </select>
                    <button
                      onClick={() => saveEdit(f.id)}
                      className="rounded bg-emerald-600 px-3 py-1 text-xs hover:bg-emerald-500"
                    >
                      Save
                    </button>
                    <button
                      onClick={() => setEditingId(null)}
                      className="rounded bg-neutral-700 px-3 py-1 text-xs hover:bg-neutral-600"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-xs text-neutral-500">{f.id.slice(0, 8)}</span>
                    <span className="flex-1">
                      {f.name} <span className="text-neutral-500">· {f.stance}</span>
                    </span>
                    <button
                      onClick={() => startEdit(f)}
                      className="text-xs text-neutral-400 hover:text-neutral-100"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => setConfirmDeleteFighter(f.id)}
                      className="text-xs text-red-400 hover:text-red-300"
                    >
                      Delete
                    </button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="rounded-lg border border-neutral-800 p-4">
        <div className="flex items-center justify-between">
          <h2 className="font-medium">
            Sessions{" "}
            <span className="text-sm text-neutral-500">
              {activeFighter === ALL
                ? `(${sessions.length} total)`
                : `(${sessions.length} for ${
                    fighters.find((f) => f.id === activeFighter)?.name ?? "selected"
                  })`}
            </span>
          </h2>
          <Link
            href="/sessions/new"
            className="rounded bg-emerald-600 px-3 py-1 text-sm font-medium hover:bg-emerald-500"
          >
            New session
          </Link>
        </div>
        {sessions.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">No sessions yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-neutral-800">
            {sessions.map((s) => (
              <li key={s.id} className="flex items-center gap-3 py-2 text-sm">
                <Link href={`/sessions/${s.id}`} className="flex-1 hover:underline">
                  <span className="font-mono text-xs text-neutral-500">{s.id.slice(0, 8)}</span>{" "}
                  · {s.source} ·{" "}
                  <span
                    className={
                      s.status === "completed"
                        ? "text-emerald-400"
                        : s.status === "failed"
                        ? "text-red-400"
                        : s.status === "capturing" || s.status === "processing"
                        ? "text-amber-400"
                        : "text-neutral-400"
                    }
                  >
                    {s.status}
                  </span>
                </Link>
                <button
                  onClick={() => setConfirmDeleteSession(s.id)}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {confirmDeleteFighter && (
        <ConfirmDialog
          title="Delete fighter?"
          body="This will also delete all of their sessions, captured pose data, uploaded videos, and detected events. Cannot be undone."
          onCancel={() => setConfirmDeleteFighter(null)}
          onConfirm={() => doDeleteFighter(confirmDeleteFighter)}
        />
      )}
      {confirmDeleteSession && (
        <ConfirmDialog
          title="Delete session?"
          body="This removes the session row, detected punch events, captured pose data, and any uploaded video file. Cannot be undone."
          onCancel={() => setConfirmDeleteSession(null)}
          onConfirm={() => doDeleteSession(confirmDeleteSession)}
        />
      )}
    </main>
  );
}

function ConfirmDialog({
  title,
  body,
  onCancel,
  onConfirm,
}: {
  title: string;
  body: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-md rounded-lg border border-neutral-800 bg-neutral-950 p-5 shadow-xl">
        <h3 className="font-medium">{title}</h3>
        <p className="mt-2 text-sm text-neutral-400">{body}</p>
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onCancel}
            className="rounded bg-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-600"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium hover:bg-red-500"
          >
            Delete
          </button>
        </div>
      </div>
    </div>
  );
}

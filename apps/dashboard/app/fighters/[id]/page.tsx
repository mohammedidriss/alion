"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Sparkline } from "@/components/Sparkline";
import {
  api,
  type Fighter,
  type PunchEvent,
  type Session,
  type Stance,
} from "@/lib/api";

interface SessionWithStats {
  session: Session;
  events: PunchEvent[];
  totalPunches: number;
  peakVelocity: number;
  meanVelocity: number;
}

export default function FighterPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const router = useRouter();
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [sessions, setSessions] = useState<SessionWithStats[]>([]);
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editStance, setEditStance] = useState<Stance>("orthodox");
  const [confirmDeleteFighter, setConfirmDeleteFighter] = useState(false);
  const [confirmDeleteSession, setConfirmDeleteSession] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, sList] = await Promise.all([api.getFighter(id), api.listSessions(id)]);
      setFighter(f);
      const withStats = await Promise.all(
        sList
          .slice()
          .sort((a, b) => a.started_at.localeCompare(b.started_at))
          .map(async (s) => {
            const evs = await api.listEvents(s.id).catch(() => [] as PunchEvent[]);
            const vels = evs.map((e) => e.velocity_ms);
            return {
              session: s,
              events: evs,
              totalPunches: evs.length,
              peakVelocity: vels.length ? Math.max(...vels) : 0,
              meanVelocity: vels.length ? vels.reduce((s, v) => s + v, 0) / vels.length : 0,
            };
          }),
      );
      setSessions(withStats);
    } catch (e) {
      setErr(String(e));
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const aggregate = useMemo(() => {
    const completed = sessions.filter((x) => x.session.status === "completed");
    const all = completed.flatMap((x) => x.events);
    const allVels = all.map((e) => e.velocity_ms);
    const totalDurationMs = completed.reduce((s, x) => s + x.session.duration_ms, 0);
    const punchesPerSession = completed.map((x) => x.totalPunches);
    const peakPerSession = completed.map((x) => x.peakVelocity);
    return {
      totalSessions: sessions.length,
      completedSessions: completed.length,
      totalPunches: all.length,
      totalDurationS: totalDurationMs / 1000,
      peakVelocity: allVels.length ? Math.max(...allVels) : 0,
      meanVelocity: allVels.length ? allVels.reduce((s, v) => s + v, 0) / allVels.length : 0,
      punchesPerSession,
      peakPerSession,
      bestByPunches: completed
        .slice()
        .sort((a, b) => b.totalPunches - a.totalPunches)
        .slice(0, 3),
      bestByPeak: completed
        .slice()
        .filter((x) => x.peakVelocity > 0)
        .sort((a, b) => b.peakVelocity - a.peakVelocity)
        .slice(0, 3),
    };
  }, [sessions]);

  if (!fighter) {
    return (
      <main className="p-8 text-sm text-neutral-400">
        {err ? <span className="text-red-400">{err}</span> : "Loading…"}
      </main>
    );
  }

  const startEdit = () => {
    setEditName(fighter.name);
    setEditStance(fighter.stance);
    setEditing(true);
  };

  const saveEdit = async () => {
    try {
      await api.updateFighter(id, { name: editName.trim(), stance: editStance });
      setEditing(false);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  const deleteFighter = async () => {
    try {
      await api.deleteFighter(id);
      router.push("/");
    } catch (e) {
      setErr(String(e));
      setConfirmDeleteFighter(false);
    }
  };

  const deleteSession = async (sid: string) => {
    try {
      await api.deleteSession(sid);
      setConfirmDeleteSession(null);
      await load();
    } catch (e) {
      setErr(String(e));
    }
  };

  return (
    <main className="mx-auto max-w-4xl space-y-8 p-8">
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm text-neutral-400 hover:text-neutral-100"
      >
        <span aria-hidden>←</span> All fighters
      </Link>

      {err && (
        <p className="rounded border border-red-700/60 bg-red-950/40 p-3 text-sm text-red-300">
          {err}
        </p>
      )}

      <header className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <h1 className="text-3xl font-semibold">{fighter.name}</h1>
          <p className="mt-1 text-sm text-neutral-400">
            {fighter.stance}
            {fighter.dob ? ` · born ${fighter.dob}` : ""}
          </p>
          <p className="mt-2 font-mono text-xs text-neutral-500">{fighter.id}</p>
          <div className="mt-4 flex gap-2">
            <Link
              href={`/sessions/new?fighter=${fighter.id}`}
              className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
            >
              New session
            </Link>
            <button
              onClick={startEdit}
              className="rounded bg-neutral-800 px-3 py-1.5 text-sm hover:bg-neutral-700"
            >
              Edit profile
            </button>
            <button
              onClick={() => setConfirmDeleteFighter(true)}
              className="rounded bg-neutral-800 px-3 py-1.5 text-sm text-red-300 hover:bg-red-900/40"
            >
              Delete
            </button>
          </div>
        </div>

        <aside className="rounded-lg border border-neutral-800 p-4">
          <h2 className="text-sm font-medium text-neutral-300">Career totals</h2>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
            <Cell label="Sessions" value={aggregate.totalSessions} />
            <Cell label="Completed" value={aggregate.completedSessions} />
            <Cell label="Total punches" value={aggregate.totalPunches} />
            <Cell
              label="Total duration"
              value={`${(aggregate.totalDurationS / 60).toFixed(1)}m`}
            />
            <Cell label="Peak velocity" value={`${aggregate.peakVelocity.toFixed(2)} m/s`} />
            <Cell label="Mean velocity" value={`${aggregate.meanVelocity.toFixed(2)} m/s`} />
          </dl>
        </aside>
      </header>

      {editing && (
        <Modal title="Edit profile" onCancel={() => setEditing(false)}>
          <input
            className="mt-3 w-full rounded bg-neutral-900 p-2 text-sm"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            placeholder="Name"
          />
          <select
            className="mt-2 w-full rounded bg-neutral-900 p-2 text-sm"
            value={editStance}
            onChange={(e) => setEditStance(e.target.value as Stance)}
          >
            <option value="orthodox">orthodox</option>
            <option value="southpaw">southpaw</option>
            <option value="switch">switch</option>
          </select>
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={() => setEditing(false)}
              className="rounded bg-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-600"
            >
              Cancel
            </button>
            <button
              onClick={saveEdit}
              className="rounded bg-emerald-600 px-3 py-1.5 text-sm font-medium hover:bg-emerald-500"
            >
              Save
            </button>
          </div>
        </Modal>
      )}

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Punches per session</h2>
          <p className="mt-1 text-xs text-neutral-500">
            Across {aggregate.completedSessions} completed session
            {aggregate.completedSessions === 1 ? "" : "s"}, oldest → newest.
          </p>
          <div className="mt-3">
            <Sparkline
              values={aggregate.punchesPerSession}
              ariaLabel="Punches per session over time"
              color="#34d399"
            />
          </div>
        </div>
        <div className="rounded-lg border border-neutral-800 p-4">
          <h2 className="font-medium">Peak velocity per session</h2>
          <p className="mt-1 text-xs text-neutral-500">m/s, oldest → newest.</p>
          <div className="mt-3">
            <Sparkline
              values={aggregate.peakPerSession}
              ariaLabel="Peak velocity per session over time"
              color="#60a5fa"
            />
          </div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <BestList
          title="Most punches"
          rows={aggregate.bestByPunches}
          metric={(s) => `${s.totalPunches}`}
          metricLabel="punches"
        />
        <BestList
          title="Hardest punch (peak velocity)"
          rows={aggregate.bestByPeak}
          metric={(s) => `${s.peakVelocity.toFixed(2)} m/s`}
          metricLabel="peak"
        />
      </section>

      <section className="rounded-lg border border-neutral-800 p-4">
        <h2 className="font-medium">All sessions ({sessions.length})</h2>
        {sessions.length === 0 ? (
          <p className="mt-2 text-sm text-neutral-500">No sessions yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-neutral-800">
            {sessions
              .slice()
              .reverse()
              .map((x) => (
                <li
                  key={x.session.id}
                  className="flex items-center gap-3 py-2 text-sm"
                >
                  <Link
                    href={`/sessions/${x.session.id}`}
                    className="flex-1 hover:underline"
                  >
                    <span className="font-mono text-xs text-neutral-500">
                      {x.session.id.slice(0, 8)}
                    </span>{" "}
                    · {new Date(x.session.started_at).toLocaleString()} ·{" "}
                    {x.session.source} ·{" "}
                    <span
                      className={
                        x.session.status === "completed"
                          ? "text-emerald-400"
                          : x.session.status === "failed"
                          ? "text-red-400"
                          : x.session.status === "capturing" ||
                            x.session.status === "processing"
                          ? "text-amber-400"
                          : "text-neutral-400"
                      }
                    >
                      {x.session.status}
                    </span>{" "}
                    <span className="text-neutral-500">
                      {x.totalPunches > 0 && `· ${x.totalPunches} punches`}
                      {x.peakVelocity > 0 && ` · peak ${x.peakVelocity.toFixed(2)} m/s`}
                    </span>
                  </Link>
                  <button
                    onClick={() => setConfirmDeleteSession(x.session.id)}
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
        <Modal
          title="Delete this fighter?"
          onCancel={() => setConfirmDeleteFighter(false)}
          danger
          onConfirm={deleteFighter}
          confirmLabel="Delete fighter"
        >
          <p className="mt-2 text-sm text-neutral-400">
            This also deletes all of {fighter.name}&apos;s sessions, captured
            pose data, uploaded videos, and detected events. Cannot be undone.
          </p>
        </Modal>
      )}
      {confirmDeleteSession && (
        <Modal
          title="Delete this session?"
          onCancel={() => setConfirmDeleteSession(null)}
          danger
          onConfirm={() => deleteSession(confirmDeleteSession)}
          confirmLabel="Delete session"
        >
          <p className="mt-2 text-sm text-neutral-400">
            Removes the session row, detected punch events, captured pose data,
            and any uploaded video. Cannot be undone.
          </p>
        </Modal>
      )}
    </main>
  );
}

function Cell({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-neutral-500">{label}</dt>
      <dd className="mt-0.5 text-lg font-semibold">{value}</dd>
    </div>
  );
}

function BestList({
  title,
  rows,
  metric,
  metricLabel,
}: {
  title: string;
  rows: SessionWithStats[];
  metric: (s: SessionWithStats) => string;
  metricLabel: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <h2 className="font-medium">{title}</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-neutral-500">Not enough data yet.</p>
      ) : (
        <ol className="mt-3 space-y-1 text-sm">
          {rows.map((x, i) => (
            <li key={x.session.id} className="flex items-center gap-3">
              <span className="font-mono text-xs text-neutral-500">{i + 1}.</span>
              <Link
                href={`/sessions/${x.session.id}`}
                className="flex-1 hover:underline"
              >
                <span className="font-mono text-xs text-neutral-500">
                  {x.session.id.slice(0, 8)}
                </span>{" "}
                · {new Date(x.session.started_at).toLocaleDateString()}
              </Link>
              <span className="font-mono">
                {metric(x)}{" "}
                <span className="text-xs text-neutral-500">{metricLabel}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Modal({
  title,
  onCancel,
  onConfirm,
  confirmLabel,
  danger,
  children,
}: {
  title: string;
  onCancel: () => void;
  onConfirm?: () => void;
  confirmLabel?: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-md rounded-lg border border-neutral-800 bg-neutral-950 p-5 shadow-xl">
        <h3 className="font-medium">{title}</h3>
        {children}
        {onConfirm && (
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={onCancel}
              className="rounded bg-neutral-700 px-3 py-1.5 text-sm hover:bg-neutral-600"
            >
              Cancel
            </button>
            <button
              onClick={onConfirm}
              className={`rounded px-3 py-1.5 text-sm font-medium ${
                danger ? "bg-red-600 hover:bg-red-500" : "bg-emerald-600 hover:bg-emerald-500"
              }`}
            >
              {confirmLabel ?? "Confirm"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

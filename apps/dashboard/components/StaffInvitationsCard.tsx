"use client";

/**
 * The signed-in person's roles at gyms (ADR-052): invitations to accept or decline,
 * and the roles they hold, which they can leave. Shows nothing when there are none.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type GymStaff } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ROLE: Record<string, string> = {
  owner: "owner",
  manager: "manager",
  head_coach: "head coach",
  coach: "coach",
};

const WHAT: Record<string, string> = {
  owner: "You'd manage its members, staff and settings, and see its fighters' training.",
  manager: "You'd manage its members and staff, and see its fighters' training.",
  head_coach: "You'd see its fighters' training and add its coaches to their support teams.",
  coach: "You'd see its fighters' profiles, and coach the fighters assigned to you.",
};

export function StaffInvitationsCard() {
  const { refreshUser } = useAuth();
  const [rows, setRows] = useState<GymStaff[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .myStaff()
      .then(setRows)
      .catch(() => setRows([]));
  }, []);
  useEffect(() => load(), [load]);

  const answer = async (r: GymStaff, a: "accept" | "decline" | "leave") => {
    if (a === "leave" && !confirm(`Leave your role as ${ROLE[r.role]} at ${r.gym_name}?`)) return;
    setBusy(r.id);
    setErr(null);
    try {
      await api.answerStaff(r.id, a);
      load();
      await refreshUser();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (rows.length === 0) return null;
  const invited = rows.filter((r) => r.status === "invited");
  const held = rows.filter((r) => r.status === "active");
  return (
    <div className={`card space-y-3 ${invited.length ? "border border-amber-500/30" : ""}`}>
      <h2 className={`text-base font-semibold ${invited.length ? "text-amber-200" : ""}`}>
        {invited.length ? "A gym invites you to its staff" : "Your roles at gyms"}
      </h2>
      {err && <p className="text-sm text-red-300">{err}</p>}
      {invited.map((r) => (
        <div key={r.id} className="space-y-2 rounded-xl border border-white/10 p-3 text-sm">
          <p className="text-neutral-100">
            <b>{r.gym_name}</b> — as {ROLE[r.role]}
            {r.invited_by_name && <span className="text-neutral-400">, invited by {r.invited_by_name}</span>}
          </p>
          <p className="text-xs text-neutral-300">{WHAT[r.role]}</p>
          <div className="flex gap-2">
            <button
              onClick={() => void answer(r, "accept")}
              disabled={busy !== null}
              className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
            >
              Accept
            </button>
            <button
              onClick={() => void answer(r, "decline")}
              disabled={busy !== null}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-40"
            >
              Decline
            </button>
          </div>
        </div>
      ))}
      {held.map((r) => (
        <div key={r.id} className="flex flex-wrap items-center justify-between gap-2 text-sm">
          <span className="text-neutral-200">
            {r.gym_name} <span className="text-neutral-500">· {ROLE[r.role]}</span>
          </span>
          <button
            onClick={() => void answer(r, "leave")}
            disabled={busy !== null}
            className="rounded-lg border border-white/15 px-2.5 py-1 text-xs text-neutral-300 hover:bg-white/5 disabled:opacity-40"
          >
            Leave
          </button>
        </div>
      ))}
    </div>
  );
}

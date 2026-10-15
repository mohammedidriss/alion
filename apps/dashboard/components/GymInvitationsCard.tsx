"use client";

/**
 * A gym asking the signed-in fighter to join it (ADR-035): who'd see their
 * training data, and Accept / Decline. Shows nothing when there's no invitation.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type GymInvitation } from "@/lib/api";

export function GymInvitationsCard({ onAnswered }: { onAnswered?: () => void }) {
  const [invites, setInvites] = useState<GymInvitation[]>([]);
  const [busy, setBusy] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rulesOk, setRulesOk] = useState<Record<number, boolean>>({});

  const load = useCallback(() => {
    api
      .gymInvitations()
      .then(setInvites)
      .catch(() => setInvites([]));
  }, []);
  useEffect(() => load(), [load]);

  const answer = async (id: number, a: "accept" | "decline") => {
    setBusy(id);
    setErr(null);
    try {
      await api.answerGymInvitation(id, a, a === "accept" ? { accept_rules: !!rulesOk[id] } : undefined);
      load();
      onAnswered?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  if (invites.length === 0) return null;
  return (
    <div className="card space-y-3 border border-amber-500/30">
      <h2 className="text-base font-semibold text-amber-200">
        {invites.length === 1 ? "A gym wants to add you" : "Gyms want to add you"}
      </h2>
      {err && <p className="text-sm text-red-300">{err}</p>}
      {invites.map((i) => (
        <div key={i.id} className="space-y-2 rounded-xl border border-white/10 p-3 text-sm">
          <p className="text-neutral-100">
            <b>{i.gym_name}</b>
            {i.gym_city && <span className="text-neutral-400"> · {i.gym_city}</span>}
            {i.invited_by && <span className="text-neutral-400"> — invited by {i.invited_by}</span>}
          </p>
          <p className="text-xs text-neutral-300">
            If you accept, the gym&apos;s managers
            {i.managers.length > 0 && <> ({i.managers.join(", ")})</>} see your training sessions, punches,
            heart rate and wrist data — never your health notes. You can leave the gym later.
          </p>
          {i.rules && (
            <div className="space-y-1">
              <div className="max-h-32 overflow-y-auto whitespace-pre-wrap rounded-lg border border-white/10 bg-black/30 p-2 text-xs text-neutral-300">{i.rules}</div>
              <label className="flex items-center gap-2 text-xs text-neutral-300">
                <input type="checkbox" checked={!!rulesOk[i.id]} onChange={(e) => setRulesOk((r) => ({ ...r, [i.id]: e.target.checked }))} />
                I accept the gym&apos;s rules
              </label>
            </div>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => void answer(i.id, "accept")}
              disabled={busy !== null || (!!i.rules && !rulesOk[i.id])}
              className="rounded-lg bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
            >
              Accept
            </button>
            <button
              onClick={() => void answer(i.id, "decline")}
              disabled={busy !== null}
              className="rounded-lg border border-white/15 px-3 py-1.5 text-sm text-neutral-200 hover:bg-white/5 disabled:opacity-40"
            >
              Decline
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

"use client";

/**
 * A gym's staff (ADR-052): who holds which role, invitations waiting for an answer,
 * inviting someone — by their account's email, or a coach by System ID — and ending
 * a role. Owners and managers change it; the server checks.
 */

import { useCallback, useEffect, useState } from "react";
import { api, type GymStaff, type GymStaffRole } from "@/lib/api";

const ROLES: { value: GymStaffRole; label: string; hint: string }[] = [
  { value: "coach", label: "Coach", hint: "coaches the fighters assigned to them" },
  { value: "head_coach", label: "Head coach", hint: "sees the gym's fighters' training; assigns its coaches" },
  { value: "manager", label: "Manager", hint: "members, staff and the gym's settings" },
  { value: "owner", label: "Owner", hint: "everything a manager does; adds owners" },
];
const LABEL = Object.fromEntries(ROLES.map((r) => [r.value, r.label])) as Record<GymStaffRole, string>;

export function StaffPanel({ gymId }: { gymId: string }) {
  const [rows, setRows] = useState<GymStaff[]>([]);
  const [who, setWho] = useState("");
  const [role, setRole] = useState<GymStaffRole>("coach");
  const [showPast, setShowPast] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .gymStaff(gymId)
      .then(setRows)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [gymId]);
  useEffect(() => load(), [load]);

  const invite = async () => {
    const v = who.trim();
    if (!v) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      const r = await api.inviteStaff(gymId, v.includes("@") ? { email: v, role } : { system_id: v, role });
      setMsg(
        r.status === "invited"
          ? `Invited ${r.name} as ${LABEL[r.role].toLowerCase()}. They accept it on their Alion home or profile page.`
          : `${r.name} is on the staff as ${LABEL[r.role].toLowerCase()}.`,
      );
      setWho("");
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const end = async (s: GymStaff) => {
    const what = s.status === "invited" ? "Withdraw the invitation to" : "End the role of";
    if (!confirm(`${what} ${s.name} as ${LABEL[s.role].toLowerCase()}? A coach's links made through the gym end too.`)) return;
    setErr(null);
    try {
      await api.endStaff(gymId, s.id);
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };

  const current = rows.filter((r) => r.status === "active" || r.status === "invited");
  const past = rows.filter((r) => r.status === "left" || r.status === "declined");
  return (
    <section className="card space-y-4">
      <div>
        <h2 className="text-base font-semibold">Staff</h2>
        <p className="text-xs text-neutral-500">
          Roles at this gym. Someone invited accepts before the role counts; a profile nobody signs in to joins at once.
        </p>
      </div>
      <ul className="divide-y divide-white/5 text-sm">
        {current.map((s) => (
          <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <span className="font-medium text-neutral-100">{s.name}</span>
              <span className="ml-2 rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-300">{LABEL[s.role]}</span>
              {s.status === "invited" && (
                <span className="ml-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-300">invited</span>
              )}
              {s.email && <div className="truncate text-xs text-neutral-500">{s.email}</div>}
            </div>
            <button
              onClick={() => void end(s)}
              className="rounded-lg px-2 py-1 text-xs text-red-400/70 hover:bg-red-500/10 hover:text-red-300"
            >
              {s.status === "invited" ? "Withdraw" : "End"}
            </button>
          </li>
        ))}
        {current.length === 0 && <li className="py-2 text-neutral-500">No staff yet.</li>}
      </ul>
      {past.length > 0 && (
        <button onClick={() => setShowPast(!showPast)} className="text-xs text-neutral-500 underline">
          {showPast ? "Hide" : "Show"} past staff ({past.length})
        </button>
      )}
      {showPast && (
        <ul className="text-xs text-neutral-500">
          {past.map((s) => (
            <li key={s.id}>
              {s.name} · {LABEL[s.role].toLowerCase()} · {s.status}
              {s.ended_at && ` ${new Date(s.ended_at).toLocaleDateString()}`}
            </li>
          ))}
        </ul>
      )}
      <div className="flex flex-col gap-2 sm:flex-row">
        <input
          value={who}
          onChange={(e) => setWho(e.target.value)}
          placeholder="Their account's email, or a coach's System ID"
          className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as GymStaffRole)}
          title={ROLES.find((r) => r.value === role)?.hint}
          className="rounded-xl border border-white/10 bg-neutral-900 px-3 py-2 text-sm text-neutral-200"
        >
          {ROLES.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
        <button
          onClick={() => void invite()}
          disabled={busy || !who.trim()}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          Invite
        </button>
      </div>
      <p className="text-xs text-neutral-500">{ROLES.find((r) => r.value === role)?.label}: {ROLES.find((r) => r.value === role)?.hint}.</p>
      {msg && <p className="text-sm text-emerald-300">{msg}</p>}
      {err && <p className="text-sm text-red-300">{err}</p>}
    </section>
  );
}

"use client";

/**
 * Squads (ADR-053): competition teams, classes and fight camps within a gym, each
 * with its fighters and its coaches. For the gym's owners, managers and head
 * coaches. A squad coach sees the squad's fighters' training while both are on it
 * and the squad is open; a camp closes after its last day.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Bout, type GymMembership, type GymStaff, type Squad, type SquadKind } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { leadsGym } from "@/lib/nav";

const KINDS: { value: SquadKind; label: string }[] = [
  { value: "competition", label: "Competition team" },
  { value: "class", label: "Class" },
  { value: "camp", label: "Fight camp" },
  { value: "other", label: "Other" },
];
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label])) as Record<SquadKind, string>;
const inputCls =
  "rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none";

function errText(e: unknown): string {
  const m = String(e instanceof Error ? e.message : e).match(/^\d{3} (.*)$/s);
  if (m) {
    try {
      const d = JSON.parse(m[1])?.detail;
      if (typeof d === "string") return d;
    } catch {
      /* fall through */
    }
  }
  return String(e instanceof Error ? e.message : e);
}

export default function SquadsPage() {
  const { user } = useAuth();
  const [gyms, setGyms] = useState<{ id: string; name: string }[]>([]);
  const [gymId, setGymId] = useState<string | null>(null);
  const [squads, setSquads] = useState<Squad[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [selected, setSelected] = useState<Squad | null>(null);
  const [members, setMembers] = useState<GymMembership[]>([]);
  const [staff, setStaff] = useState<GymStaff[]>([]);
  const [err, setErr] = useState<string | null>(null);
  // new squad
  const [name, setName] = useState("");
  const [kind, setKind] = useState<SquadKind>("competition");
  const [level, setLevel] = useState("");
  const [endsOn, setEndsOn] = useState("");
  const [boutId, setBoutId] = useState("");
  const [bouts, setBouts] = useState<Bout[]>([]);
  // adding to the selected squad
  const [addFighter, setAddFighter] = useState("");
  const [addMain, setAddMain] = useState(false);
  const [addCoach, setAddCoach] = useState("");
  const [addRole, setAddRole] = useState<"coach" | "head_coach">("coach");

  // The gyms this person runs squads at.
  useEffect(() => {
    if (!user) return;
    const led = (user.gym_roles ?? []).filter((r) => ["owner", "manager", "head_coach"].includes(r.role));
    const unique = Array.from(new Map(led.map((r) => [r.gym_id, { id: r.gym_id, name: r.gym_name }])).values());
    if (unique.length > 0) {
      setGyms(unique);
      setGymId((g) => g ?? unique[0].id);
    } else if (user.role === "gym_manager") {
      api
        .getMyGymManagerProfile()
        .then((m) => {
          setGyms([{ id: m.gym_id, name: m.gym_name }]);
          setGymId(m.gym_id);
        })
        .catch((e) => setErr(errText(e)));
    }
  }, [user]);

  useEffect(() => {
    api
      .listBouts()
      .then((b) => setBouts(b.slice().sort((x, y) => x.scheduled_at.localeCompare(y.scheduled_at))))
      .catch(() => setBouts([]));
  }, []);

  const load = useCallback(() => {
    if (!gymId) return;
    api
      .gymSquads(gymId, showArchived)
      .then(setSquads)
      .catch((e) => setErr(errText(e)));
    api.listGymMembers(gymId).then(setMembers).catch(() => setMembers([]));
    api.gymStaff(gymId).then(setStaff).catch(() => setStaff([]));
  }, [gymId, showArchived]);
  useEffect(() => load(), [load]);

  const refresh = (s: Squad) => {
    setSelected(s);
    load();
  };
  const act = async (fn: () => Promise<Squad>) => {
    setErr(null);
    try {
      refresh(await fn());
    } catch (e) {
      setErr(errText(e));
    }
  };

  const create = async () => {
    if (!gymId || !name.trim()) return;
    await act(() =>
      api.createSquad(gymId, {
        name: name.trim(),
        kind,
        level: level.trim() || null,
        ends_on: endsOn || null,
        bout_id: kind === "camp" && boutId ? boutId : null,
      }),
    );
    setName("");
    setLevel("");
    setEndsOn("");
    setBoutId("");
  };

  const open = async (s: Squad) => {
    setErr(null);
    try {
      setSelected(await api.getSquad(s.id));
    } catch (e) {
      setErr(errText(e));
    }
  };

  const onSquad = useMemo(() => new Set(selected?.members?.map((m) => m.fighter_id) ?? []), [selected]);
  const coaching = useMemo(() => new Set(selected?.staff?.map((c) => c.coach_id) ?? []), [selected]);
  const fighterChoices = members.filter(
    (m) => m.member_type === "fighter" && ["active", "trial", "frozen", "suspended"].includes(m.status) && !onSquad.has(m.member_id),
  );
  const coachChoices = staff.filter(
    (s) => s.status === "active" && s.coach_id && (s.role === "coach" || s.role === "head_coach") && !coaching.has(s.coach_id),
  );

  if (user && !leadsGym(user)) {
    return <div className="px-4 py-8 text-neutral-400 sm:px-8">Squads are run by a gym&apos;s owners, managers and head coaches.</div>;
  }

  return (
    <div className="space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Squads</h1>
          <p className="text-sm text-neutral-500">
            Teams, classes and fight camps. A squad&apos;s coaches see its fighters&apos; training while both are on it.
          </p>
        </div>
        {gyms.length > 1 && (
          <select value={gymId ?? ""} onChange={(e) => { setGymId(e.target.value); setSelected(null); }} className={inputCls}>
            {gyms.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        )}
      </header>

      {err && <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>}

      <section className="card space-y-3">
        <h2 className="text-base font-semibold">New squad</h2>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name, e.g. Pro team" className={inputCls} />
          <select value={kind} onChange={(e) => setKind(e.target.value as SquadKind)} className={inputCls}>
            {KINDS.map((k) => (
              <option key={k.value} value={k.value}>{k.label}</option>
            ))}
          </select>
          <input value={level} onChange={(e) => setLevel(e.target.value)} placeholder="Level (optional)" className={inputCls} />
          <input
            type="date"
            value={endsOn}
            onChange={(e) => setEndsOn(e.target.value)}
            title={kind === "camp" ? "The camp's last day" : "Optional last day"}
            className={inputCls}
          />
        </div>
        <button
          onClick={() => void create()}
          disabled={!name.trim() || !gymId}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
        >
          Create
        </button>
        {kind === "camp" && (
          <div className="flex flex-wrap items-center gap-2">
            <select value={boutId} onChange={(e) => setBoutId(e.target.value)} className={inputCls}>
              <option value="">For a bout (optional)…</option>
              {bouts.map((b) => (
                <option key={b.id} value={b.id}>
                  {(b.label || "Bout") + " — " + new Date(b.scheduled_at).toLocaleDateString()}
                </option>
              ))}
            </select>
            <p className="text-xs text-neutral-500">
              A camp ends on its bout&apos;s day unless you give a last day; its coaches stop seeing its fighters after it.
            </p>
          </div>
        )}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-3">
          {squads.map((s) => (
            <button
              key={s.id}
              onClick={() => void open(s)}
              className={`card block w-full text-left transition-colors hover:bg-white/[0.04] ${selected?.id === s.id ? "ring-1 ring-emerald-500/60" : ""}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-medium text-neutral-100">{s.name}</span>
                <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-300">{KIND_LABEL[s.kind]}</span>
                {s.level && <span className="text-xs text-neutral-500">{s.level}</span>}
                {!s.open && <span className="rounded-full bg-neutral-500/15 px-2 py-0.5 text-[10px] text-neutral-400">closed</span>}
              </div>
              <div className="mt-1 text-xs text-neutral-400">
                {s.fighters} fighter{s.fighters === 1 ? "" : "s"}
                {s.coaches.length > 0 && ` · ${s.coaches.join(", ")}`}
                {s.ends_on && ` · until ${new Date(s.ends_on).toLocaleDateString()}`}
                {s.bout_label && ` · for ${s.bout_label}`}
              </div>
              {s.trained_7d !== null && (
                <div className="mt-1 text-xs text-neutral-500">
                  This week: {s.trained_7d} of {s.fighters} trained · {s.checked_in_7d ?? 0} checked in · {s.sessions_7d} session
                  {s.sessions_7d === 1 ? "" : "s"} with the squad
                </div>
              )}
            </button>
          ))}
          {squads.length === 0 && <p className="card text-sm text-neutral-500">No squads yet.</p>}
          <label className="flex items-center gap-2 text-xs text-neutral-500">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            Show archived squads
          </label>
        </section>

        {selected && (
          <section className="card space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h2 className="text-lg font-semibold">{selected.name}</h2>
                <p className="text-xs text-neutral-500">
                  {KIND_LABEL[selected.kind]}
                  {selected.ends_on && ` · until ${new Date(selected.ends_on).toLocaleDateString()}`}
                  {selected.bout_label && ` · for ${selected.bout_label}`}
                  {!selected.open && " · closed"}
                </p>
              </div>
              {selected.archived_at === null && (
                <button
                  onClick={() => {
                    if (confirm(`Archive ${selected.name}? Its coaches stop seeing its fighters through it.`))
                      void act(() => api.archiveSquad(selected.id));
                  }}
                  className="rounded-lg border border-white/15 px-2.5 py-1 text-xs text-neutral-300 hover:bg-white/5"
                >
                  Archive
                </button>
              )}
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-neutral-300">Fighters</h3>
              <ul className="divide-y divide-white/5 text-sm">
                {selected.members?.map((m) => (
                  <li key={m.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                    <span>
                      <Link href={`/fighters/${m.fighter_id}`} className="hover:underline">{m.name}</Link>
                      {m.is_main && <span className="ml-2 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">main squad</span>}
                    </span>
                    <span className="flex gap-1">
                      {!m.is_main && (
                        <button onClick={() => void act(() => api.setMainSquad(selected.id, m.id, true))} className="rounded-lg px-2 py-1 text-xs text-neutral-400 hover:bg-white/5">
                          Make main
                        </button>
                      )}
                      <button onClick={() => void act(() => api.endSquadMember(selected.id, m.id))} className="rounded-lg px-2 py-1 text-xs text-red-400/70 hover:bg-red-500/10">
                        Remove
                      </button>
                    </span>
                  </li>
                ))}
                {selected.members?.length === 0 && <li className="py-1.5 text-neutral-500">No fighters yet.</li>}
              </ul>
              {selected.open && (
                <div className="flex flex-wrap items-center gap-2">
                  <select value={addFighter} onChange={(e) => setAddFighter(e.target.value)} className={`${inputCls} flex-1`}>
                    <option value="">Add one of the gym&apos;s fighters…</option>
                    {fighterChoices.map((m) => (
                      <option key={m.member_id} value={m.member_id}>{m.member_name}</option>
                    ))}
                  </select>
                  <label className="flex items-center gap-1 text-xs text-neutral-400">
                    <input type="checkbox" checked={addMain} onChange={(e) => setAddMain(e.target.checked)} /> main squad
                  </label>
                  <button
                    disabled={!addFighter}
                    onClick={() => {
                      void act(() => api.addSquadMember(selected.id, addFighter, addMain));
                      setAddFighter("");
                      setAddMain(false);
                    }}
                    className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
                  >
                    Add
                  </button>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <h3 className="text-sm font-semibold text-neutral-300">Coaches</h3>
              <ul className="divide-y divide-white/5 text-sm">
                {selected.staff?.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-2 py-1.5">
                    <span>
                      <Link href={`/coaches/${c.coach_id}`} className="hover:underline">{c.name}</Link>
                      <span className="ml-2 text-xs text-neutral-500">{c.role === "head_coach" ? "head coach" : "coach"}</span>
                    </span>
                    <button onClick={() => void act(() => api.endSquadCoach(selected.id, c.id))} className="rounded-lg px-2 py-1 text-xs text-red-400/70 hover:bg-red-500/10">
                      Remove
                    </button>
                  </li>
                ))}
                {selected.staff?.length === 0 && <li className="py-1.5 text-neutral-500">No coaches yet.</li>}
              </ul>
              {selected.open && (
                <div className="flex flex-wrap items-center gap-2">
                  <select value={addCoach} onChange={(e) => setAddCoach(e.target.value)} className={`${inputCls} flex-1`}>
                    <option value="">Add one of the gym&apos;s coaches…</option>
                    {coachChoices.map((s) => (
                      <option key={s.id} value={s.coach_id ?? ""}>{s.name}</option>
                    ))}
                  </select>
                  <select value={addRole} onChange={(e) => setAddRole(e.target.value as "coach" | "head_coach")} className={inputCls}>
                    <option value="coach">Coach</option>
                    <option value="head_coach">Head coach</option>
                  </select>
                  <button
                    disabled={!addCoach}
                    onClick={() => {
                      void act(() => api.addSquadCoach(selected.id, addCoach, addRole));
                      setAddCoach("");
                    }}
                    className="rounded-xl bg-emerald-500 px-3 py-2 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-40"
                  >
                    Add
                  </button>
                </div>
              )}
              {coachChoices.length === 0 && selected.open && (
                <p className="text-xs text-neutral-500">Coaches join the gym&apos;s staff first (Staff page).</p>
              )}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

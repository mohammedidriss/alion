"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type Fighter,
  type FighterReadiness,
  type Gym,
  type GymManager,
  type Session,
} from "@/lib/api";
import { useActiveProfile } from "@/lib/activeProfile";

type RosterRow = {
  id: string;
  name: string;
  photo_path: string | null;
  role: "fighter" | "coach";
  skill_level: string | null;
  stance: string | null;
  lastActivity: string | null;
  sessionCount: number;
  readiness: FighterReadiness | null;
};

export default function GymDashboardPage() {
  const router = useRouter();
  const { active, activeRole } = useActiveProfile();
  const isGymManager = activeRole === "gym_manager";

  const [gym, setGym] = useState<Gym | null>(null);
  const [rows, setRows] = useState<RosterRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [managers, setManagers] = useState<GymManager[]>([]);
  const [filterSkill, setFilterSkill] = useState("");
  const [filterStance, setFilterStance] = useState("");
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    if (!isGymManager || !active) return;
    setLoading(true);
    try {
      const gms = await api.listGymManagers();
      setManagers(gms);
      const me = gms.find((gm) => gm.id === active.id);
      if (!me) return;
      const gymId = me.gym_id;

      const [g, fighters, coaches, sessions] = await Promise.all([
        api.getGym(gymId),
        api.listFighters(gymId),
        api.listCoaches(gymId),
        api.listSessions(),
      ]);
      setGym(g);

      // Build session counts per fighter
      const counts = new Map<string, { n: number; last: string | null }>();
      for (const s of sessions) {
        const cur = counts.get(s.fighter_id) ?? { n: 0, last: null };
        cur.n += 1;
        if (!cur.last || s.started_at > cur.last) cur.last = s.started_at;
        counts.set(s.fighter_id, cur);
      }

      // Fetch readiness for each fighter (parallel, non-fatal)
      const readinessMap = new Map<string, FighterReadiness | null>();
      const readinessResults = await Promise.allSettled(
        fighters.map((f) => api.fighterReadiness(f.id)),
      );
      fighters.forEach((f, i) => {
        const r = readinessResults[i];
        readinessMap.set(
          f.id,
          r.status === "fulfilled" ? r.value : null,
        );
      });

      const rosterRows: RosterRow[] = [
        ...fighters.map((f): RosterRow => {
          const c = counts.get(f.id) ?? { n: 0, last: null };
          return {
            id: f.id,
            name: f.name,
            photo_path: f.photo_path,
            role: "fighter",
            skill_level: f.skill_level,
            stance: f.stance,
            lastActivity: c.last,
            sessionCount: c.n,
            readiness: readinessMap.get(f.id) ?? null,
          };
        }),
        ...coaches.map((c): RosterRow => ({
          id: c.id,
          name: c.name,
          photo_path: c.photo_path,
          role: "coach",
          skill_level: null,
          stance: null,
          lastActivity: null,
          sessionCount: 0,
          readiness: null,
        })),
      ];
      // Sort: fighters with recent activity first, then coaches
      rosterRows.sort((a, b) => {
        if (a.role !== b.role) return a.role === "fighter" ? -1 : 1;
        return (b.lastActivity ?? "").localeCompare(a.lastActivity ?? "");
      });
      setRows(rosterRows);
    } finally {
      setLoading(false);
    }
  }, [active, isGymManager]);

  useEffect(() => {
    load();
  }, [load]);

  // Redirect non-gym-managers
  useEffect(() => {
    if (!isGymManager && activeRole !== null) {
      router.push("/");
    }
  }, [isGymManager, activeRole, router]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        if (filterSkill && r.skill_level !== filterSkill) return false;
        if (filterStance && r.stance !== filterStance) return false;
        if (q && !r.name.toLowerCase().includes(q)) return false;
        return true;
      }),
    [rows, filterSkill, filterStance, q],
  );

  // Aggregate readiness
  const avgReadiness = useMemo(() => {
    const scores = rows
      .filter((r) => r.readiness?.z != null)
      .map((r) => r.readiness!.z!);
    if (scores.length === 0) return null;
    return scores.reduce((a, b) => a + b, 0) / scores.length;
  }, [rows]);

  const fighterCount = rows.filter((r) => r.role === "fighter").length;
  const coachCount = rows.filter((r) => r.role === "coach").length;

  // Unique skill levels and stances for filters
  const skillLevels = useMemo(
    () =>
      [...new Set(rows.map((r) => r.skill_level).filter(Boolean))] as string[],
    [rows],
  );
  const stances = useMemo(
    () =>
      [...new Set(rows.map((r) => r.stance).filter(Boolean))] as string[],
    [rows],
  );

  if (!isGymManager) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-12 text-neutral-400">
        Sign in as a gym manager to access this dashboard.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-12 text-neutral-400">
        Loading gym dashboard…
      </div>
    );
  }

  const readinessColor = (z: number | null) => {
    if (z == null) return "text-neutral-500";
    if (z >= 0.5) return "text-emerald-400";
    if (z >= -0.5) return "text-amber-400";
    return "text-red-400";
  };

  const readinessLabel = (z: number | null) => {
    if (z == null) return "N/A";
    if (z >= 0.5) return "Ready";
    if (z >= -0.5) return "Moderate";
    return "Fatigued";
  };

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-8 py-8">
      <Link
        href="/"
        className="text-sm text-neutral-500 hover:text-neutral-300"
      >
        ← Back to roster
      </Link>

      {/* Header */}
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">{gym?.name ?? "Gym"}</h1>
          <p className="text-sm text-neutral-500">
            {[gym?.city, gym?.country].filter(Boolean).join(", ") || "No location"}{" "}
            · {fighterCount} fighter{fighterCount !== 1 ? "s" : ""}, {coachCount} coach{coachCount !== 1 ? "es" : ""}
          </p>
        </div>
        {gym && (
          <Link
            href={`/gyms/${gym.id}`}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-neutral-300 hover:bg-white/[0.07]"
          >
            Gym profile →
          </Link>
        )}
      </header>

      {/* Aggregate Metrics */}
      <div className="grid grid-cols-3 gap-4">
        <div className="card text-center">
          <p className="text-xs text-neutral-500 uppercase tracking-wider">
            Total Headcount
          </p>
          <p className="mt-1 text-3xl font-bold">{rows.length}</p>
        </div>
        <div className="card text-center">
          <p className="text-xs text-neutral-500 uppercase tracking-wider">
            Total Sessions
          </p>
          <p className="mt-1 text-3xl font-bold">
            {rows.reduce((sum, r) => sum + r.sessionCount, 0)}
          </p>
        </div>
        <div className="card text-center">
          <p className="text-xs text-neutral-500 uppercase tracking-wider">
            Avg. Gym Readiness
          </p>
          <p
            className={`mt-1 text-3xl font-bold ${readinessColor(avgReadiness)}`}
          >
            {avgReadiness != null
              ? `${avgReadiness > 0 ? "+" : ""}${avgReadiness.toFixed(2)} z`
              : "—"}
          </p>
          {avgReadiness != null && (
            <p className={`text-xs ${readinessColor(avgReadiness)}`}>
              {readinessLabel(avgReadiness)}
            </p>
          )}
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-[200px] max-w-sm">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name…"
            className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-violet-500/40 focus:outline-none"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">
            ⌕
          </span>
        </div>
        {skillLevels.length > 0 && (
          <select
            value={filterSkill}
            onChange={(e) => setFilterSkill(e.target.value)}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-300"
          >
            <option value="">All skill levels</option>
            {skillLevels.map((s) => (
              <option key={s} value={s}>
                {s.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        )}
        {stances.length > 0 && (
          <select
            value={filterStance}
            onChange={(e) => setFilterStance(e.target.value)}
            className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-neutral-300"
          >
            <option value="">All stances</option>
            {stances.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
        <span className="text-xs text-neutral-500">
          {filtered.length} of {rows.length} shown
        </span>
      </div>

      {/* Roster Table */}
      <div className="card overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wider text-neutral-500">
              <th className="pb-2 pr-4">Name</th>
              <th className="pb-2 pr-4">Role</th>
              <th className="pb-2 pr-4">Skill Level</th>
              <th className="pb-2 pr-4">Stance</th>
              <th className="pb-2 pr-4">Sessions</th>
              <th className="pb-2 pr-4">Last Activity</th>
              <th className="pb-2">Readiness</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => (
              <tr
                key={`${r.role}-${r.id}`}
                className="border-b border-white/[0.03] hover:bg-white/[0.02]"
              >
                <td className="py-3 pr-4">
                  <Link
                    href={`/${r.role === "fighter" ? "fighters" : "coaches"}/${r.id}`}
                    className="flex items-center gap-2 hover:text-violet-300"
                  >
                    <ProfileAvatar
                      name={r.name}
                      photo_path={r.photo_path}
                      size={32}
                    />
                    <span className="font-medium">{r.name}</span>
                  </Link>
                </td>
                <td className="py-3 pr-4">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      r.role === "fighter"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-blue-500/15 text-blue-300"
                    }`}
                  >
                    {r.role}
                  </span>
                </td>
                <td className="py-3 pr-4 text-neutral-400">
                  {r.skill_level?.replace(/_/g, " ") ?? "—"}
                </td>
                <td className="py-3 pr-4 text-neutral-400">
                  {r.stance ?? "—"}
                </td>
                <td className="py-3 pr-4 text-neutral-400">
                  {r.sessionCount || "—"}
                </td>
                <td className="py-3 pr-4 text-neutral-400">
                  {r.lastActivity
                    ? new Date(r.lastActivity).toLocaleDateString()
                    : "—"}
                </td>
                <td className="py-3">
                  {r.readiness?.z != null ? (
                    <span className={readinessColor(r.readiness.z)}>
                      {r.readiness.z > 0 ? "+" : ""}
                      {r.readiness.z.toFixed(2)} z ·{" "}
                      {readinessLabel(r.readiness.z)}
                    </span>
                  ) : (
                    <span className="text-neutral-600">—</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="py-8 text-center text-neutral-500"
                >
                  {rows.length === 0
                    ? "No fighters or coaches in this gym yet."
                    : "No results match your filters."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type CheckIn,
  type Coach,
  type Fighter,
  type FighterReadiness,
  type FighterTitle,
  type Gym,
  type GymManager,
  type Session,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function GymDashboardPage() {
  const router = useRouter();
  const { user } = useAuth();
  const isGymManager = user?.role === "gym_manager";

  const [gym, setGym] = useState<Gym | null>(null);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [titles, setTitles] = useState<FighterTitle[]>([]);
  const [readinessMap, setReadinessMap] = useState<Map<string, FighterReadiness | null>>(new Map());
  const [allGyms, setAllGyms] = useState<Gym[]>([]);
  const [todaysCheckins, setTodaysCheckins] = useState<CheckIn[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!isGymManager || !user) return;
    setLoading(true);
    try {
      const me = await api.getMyGymManagerProfile();
      const gymId = me.gym_id;

      const [g, fs, cs, ss, gyms] = await Promise.all([
        api.getGym(gymId),
        api.listFighters(gymId),
        api.listCoaches(gymId),
        api.listSessions(),
        api.listGyms(),
      ]);
      setGym(g);
      setFighters(fs);
      setCoaches(cs);
      setSessions(ss);
      setAllGyms(gyms);

      // Today's attendance
      try {
        const checkins = await api.listTodaysCheckins(gymId);
        setTodaysCheckins(checkins);
      } catch { /* ok if no checkins */ }

      // Fetch titles for all fighters
      const titleResults = await Promise.allSettled(
        fs.map((f) => api.listTitles(f.id)),
      );
      const allTitles: FighterTitle[] = [];
      titleResults.forEach((r) => {
        if (r.status === "fulfilled") allTitles.push(...r.value);
      });
      setTitles(allTitles);

      // Fetch readiness
      const rMap = new Map<string, FighterReadiness | null>();
      const readinessResults = await Promise.allSettled(
        fs.map((f) => api.fighterReadiness(f.id)),
      );
      fs.forEach((f, i) => {
        const r = readinessResults[i];
        rMap.set(f.id, r.status === "fulfilled" ? r.value : null);
      });
      setReadinessMap(rMap);
    } finally {
      setLoading(false);
    }
  }, [user, isGymManager]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    if (user && !isGymManager) router.push("/");
  }, [isGymManager, user, router]);

  // Derived stats
  const gymSessions = useMemo(() => {
    const fighterIds = new Set(fighters.map((f) => f.id));
    return sessions.filter((s) => fighterIds.has(s.fighter_id));
  }, [sessions, fighters]);

  const totalSessionCount = gymSessions.length;

  const activeTitles = titles.filter((t) => t.status === "active");

  const avgReadiness = useMemo(() => {
    const scores = [...readinessMap.values()]
      .filter((r): r is FighterReadiness => r?.z != null)
      .map((r) => r.z!);
    if (scores.length === 0) return null;
    return scores.reduce((a, b) => a + b, 0) / scores.length;
  }, [readinessMap]);

  // Recent sessions (last 5)
  const recentSessions = useMemo(() => {
    return [...gymSessions]
      .sort((a, b) => (b.started_at ?? "").localeCompare(a.started_at ?? ""))
      .slice(0, 5);
  }, [gymSessions]);

  // Fighters by skill level distribution
  const skillDist = useMemo(() => {
    const dist = new Map<string, number>();
    fighters.forEach((f) => {
      const lvl = f.skill_level?.replace(/_/g, " ") ?? "unset";
      dist.set(lvl, (dist.get(lvl) ?? 0) + 1);
    });
    return [...dist.entries()].sort((a, b) => b[1] - a[1]);
  }, [fighters]);

  // Stance distribution
  const stanceDist = useMemo(() => {
    const dist = new Map<string, number>();
    fighters.forEach((f) => {
      const s = f.stance ?? "unset";
      dist.set(s, (dist.get(s) ?? 0) + 1);
    });
    return [...dist.entries()].sort((a, b) => b[1] - a[1]);
  }, [fighters]);

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

  if (!isGymManager) {
    return (
      <div className="px-4 py-8 sm:px-8 sm:py-12 text-neutral-400">
        Sign in as a gym manager to access this dashboard.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="px-4 py-8 sm:px-8 sm:py-12 text-neutral-400">Loading dashboard...</div>
    );
  }

  return (
    <div className="space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      {/* Header */}
      <header>
        <h1 className="text-2xl font-bold">{gym?.name ?? "Gym"} Dashboard</h1>
        <p className="text-sm text-neutral-500">
          {[gym?.city, gym?.country].filter(Boolean).join(", ") || "No location set"}
        </p>
      </header>

      {/* KPI cards */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="card text-center">
          <p className="text-xs uppercase tracking-wider text-neutral-500">Fighters</p>
          <p className="mt-1 text-3xl font-bold">{fighters.length}</p>
        </div>
        <div className="card text-center">
          <p className="text-xs uppercase tracking-wider text-neutral-500">Coaches</p>
          <p className="mt-1 text-3xl font-bold">{coaches.length}</p>
        </div>
        <div className="card text-center">
          <p className="text-xs uppercase tracking-wider text-neutral-500">Total Sessions</p>
          <p className="mt-1 text-3xl font-bold">{gymSessions.length}</p>
        </div>
        <div className="card text-center">
          <p className="text-xs uppercase tracking-wider text-neutral-500">Avg Readiness</p>
          <p className={`mt-1 text-3xl font-bold ${readinessColor(avgReadiness)}`}>
            {avgReadiness != null
              ? `${avgReadiness > 0 ? "+" : ""}${avgReadiness.toFixed(2)}z`
              : "—"}
          </p>
          {avgReadiness != null && (
            <p className={`text-xs ${readinessColor(avgReadiness)}`}>
              {readinessLabel(avgReadiness)}
            </p>
          )}
        </div>
      </div>

      {/* Today's Attendance */}
      <div className="card">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Today&apos;s Attendance</h3>
          <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
            {todaysCheckins.length} check-in{todaysCheckins.length !== 1 ? "s" : ""}
          </span>
        </div>
        {todaysCheckins.length === 0 ? (
          <p className="mt-4 text-sm text-neutral-500">No one has checked in today yet.</p>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {todaysCheckins.map((ci) => {
              const f = fighters.find((f) => f.id === ci.member_id);
              return (
                <div
                  key={ci.id}
                  className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] p-2.5"
                >
                  <ProfileAvatar name={ci.member_name} photo_path={f?.photo_path ?? null} size={28} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium">{ci.member_name}</p>
                    <p className="text-[10px] text-neutral-500">
                      {new Date(ci.checked_in_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                      {ci.checked_out_at
                        ? ` – ${new Date(ci.checked_out_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
                        : " · in gym"}
                    </p>
                  </div>
                  {!ci.checked_out_at && (
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" title="Currently in gym" />
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Second row: Titles + Quick links */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Active Titles / Trophies */}
        <div className="card">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Active Titles</h3>
            <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium text-amber-300">
              {activeTitles.length} title{activeTitles.length !== 1 ? "s" : ""}
            </span>
          </div>
          {activeTitles.length === 0 ? (
            <p className="mt-4 text-sm text-neutral-500">No active titles held by gym fighters.</p>
          ) : (
            <ul className="mt-3 space-y-2">
              {activeTitles.map((t) => {
                const f = fighters.find((f) => f.id === t.fighter_id);
                return (
                  <li
                    key={t.id}
                    className="flex items-center gap-3 rounded-lg border border-white/5 bg-white/[0.02] p-2.5"
                  >
                    <span className="text-lg">🏆</span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium">{t.name}</p>
                      <p className="text-[11px] text-neutral-500">
                        {t.organization ?? ""}{t.weight_class ? ` · ${t.weight_class}` : ""}
                        {f ? ` — ${f.name}` : ""}
                      </p>
                    </div>
                    {t.won_on && (
                      <span className="text-[10px] text-neutral-600">
                        since {new Date(t.won_on).toLocaleDateString()}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Skill Level Distribution */}
        <div className="card">
          <h3 className="font-semibold">Fighter Breakdown</h3>
          <div className="mt-3 space-y-3">
            <div>
              <p className="mb-1.5 text-[10px] uppercase tracking-wider text-neutral-500">By Skill Level</p>
              {skillDist.map(([level, count]) => (
                <div key={level} className="flex items-center justify-between py-1">
                  <span className="text-sm capitalize text-neutral-300">{level}</span>
                  <div className="flex items-center gap-2">
                    <div className="h-1.5 rounded-full bg-emerald-500/30" style={{ width: `${Math.max(16, (count / fighters.length) * 120)}px` }}>
                      <div
                        className="h-full rounded-full bg-emerald-500"
                        style={{ width: "100%" }}
                      />
                    </div>
                    <span className="w-6 text-right text-xs text-neutral-500">{count}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="border-t border-white/5 pt-3">
              <p className="mb-1.5 text-[10px] uppercase tracking-wider text-neutral-500">By Stance</p>
              {stanceDist.map(([stance, count]) => (
                <div key={stance} className="flex items-center justify-between py-1">
                  <span className="text-sm capitalize text-neutral-300">{stance}</span>
                  <span className="text-xs text-neutral-500">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Roster readiness overview */}
      <div className="card">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Fighter Readiness</h3>
          <Link
            href="/gym-dashboard/members"
            className="text-xs text-emerald-400 hover:text-emerald-300"
          >
            View all members →
          </Link>
        </div>
        {fighters.length === 0 ? (
          <p className="mt-4 text-sm text-neutral-500">No fighters yet.</p>
        ) : (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            {fighters.map((f) => {
              const r = readinessMap.get(f.id);
              return (
                <Link
                  key={f.id}
                  href={`/fighters/${f.id}`}
                  className="flex items-center gap-2 rounded-lg border border-white/5 bg-white/[0.02] p-2.5 hover:border-white/15 hover:bg-white/[0.04]"
                >
                  <ProfileAvatar name={f.name} photo_path={f.photo_path} size={28} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium">{f.name}</p>
                    <p className={`text-[10px] ${readinessColor(r?.z ?? null)}`}>
                      {r?.z != null
                        ? `${r.z > 0 ? "+" : ""}${r.z.toFixed(1)}z · ${readinessLabel(r.z)}`
                        : "No data"}
                    </p>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      {/* Recent Sessions */}
      <div className="card">
        <h3 className="font-semibold">Recent Sessions</h3>
        {recentSessions.length === 0 ? (
          <p className="mt-4 text-sm text-neutral-500">No sessions recorded yet.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/5 text-left text-xs uppercase tracking-wider text-neutral-500">
                  <th className="pb-2 pr-4">Fighter</th>
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Source</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2">Duration</th>
                </tr>
              </thead>
              <tbody>
                {recentSessions.map((s) => {
                  const f = fighters.find((f) => f.id === s.fighter_id);
                  return (
                    <tr
                      key={s.id}
                      className="border-b border-white/[0.03] hover:bg-white/[0.02] cursor-pointer"
                      onClick={() => router.push(`/sessions/${s.id}`)}
                    >
                      <td className="py-2.5 pr-4">
                        <div className="flex items-center gap-2">
                          {f && <ProfileAvatar name={f.name} photo_path={f.photo_path} size={24} />}
                          <span className="text-neutral-300">{f?.name ?? "Unknown"}</span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-4 text-neutral-400">
                        {s.started_at ? new Date(s.started_at).toLocaleDateString() : "—"}
                      </td>
                      <td className="py-2.5 pr-4 text-neutral-400">
                        {s.source?.replace(/_/g, " ") ?? "—"}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                            s.status === "completed"
                              ? "bg-emerald-500/15 text-emerald-300"
                              : s.status === "failed"
                                ? "bg-red-500/15 text-red-300"
                                : "bg-amber-500/15 text-amber-300"
                          }`}
                        >
                          {s.status}
                        </span>
                      </td>
                      <td className="py-2.5 text-neutral-400">
                        {s.duration_ms ? `${Math.round(s.duration_ms / 1000)}s` : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Gym network (if multiple gyms) */}
      {allGyms.length > 1 && (
        <div className="card">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold">Gym Network</h3>
            <Link
              href="/gym-dashboard/gyms"
              className="text-xs text-emerald-400 hover:text-emerald-300"
            >
              Manage gyms →
            </Link>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-3">
            {allGyms.map((g) => (
              <Link
                key={g.id}
                href={`/gyms/${g.id}`}
                className={`rounded-lg border p-3 hover:bg-white/[0.04] ${
                  g.id === gym?.id
                    ? "border-emerald-500/30 bg-emerald-500/5"
                    : "border-white/5 bg-white/[0.02]"
                }`}
              >
                <p className="text-sm font-medium">{g.name}</p>
                <p className="text-[11px] text-neutral-500">
                  {[g.city, g.country].filter(Boolean).join(", ") || "No location"}
                </p>
                {g.id === gym?.id && (
                  <span className="mt-1 inline-block rounded-full bg-emerald-500/15 px-2 py-0.5 text-[9px] font-medium text-emerald-300">
                    Your gym
                  </span>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlionWordmark } from "@/components/AlionLogo";
import { CreateProfileModal } from "@/components/CreateProfileModal";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type Fighter,
  type Gym,
  type GymManager,
  type Referee,
} from "@/lib/api";
import { type ProfileKind, useActiveProfile } from "@/lib/activeProfile";

export default function Home() {
  const router = useRouter();
  const { active, activeRole, setActive } = useActiveProfile();

  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [referees, setReferees] = useState<Referee[]>([]);
  const [gyms, setGyms] = useState<Gym[]>([]);
  const [gymManagers, setGymManagers] = useState<GymManager[]>([]);
  const [health, setHealth] = useState<{ status: string; schema_version: string } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [creating, setCreating] = useState<ProfileKind | "gym" | "gym_manager" | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    try {
      const [hRes, fs, cs, rs, gs, gms] = await Promise.all([
        fetch(`${process.env.NEXT_PUBLIC_API_URL}/health`, { cache: "no-store" })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null),
        api.listFighters(),
        api.listCoaches(),
        api.listReferees(),
        api.listGyms(),
        api.listGymManagers(),
      ]);
      setHealth(hRes);
      setFighters(fs);
      setCoaches(cs);
      setReferees(rs);
      setGyms(gs);
      setGymManagers(gms);
    } catch (e) {
      setErr(String(e));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const isAdmin = activeRole === "admin";
  const isGymManager = activeRole === "gym_manager";
  const myGymId = isGymManager
    ? gymManagers.find((gm) => gm.id === active?.id)?.gym_id ?? null
    : null;
  const myGym = myGymId ? gyms.find((g) => g.id === myGymId) ?? null : null;

  // All signable profiles
  const allProfiles = useMemo(() => {
    const list: { kind: ProfileKind; id: string; name: string; photo_path: string | null; detail: string }[] = [];
    for (const f of fighters) {
      list.push({ kind: "fighter", id: f.id, name: f.name, photo_path: f.photo_path, detail: [f.stance, f.weight_class].filter(Boolean).join(" · ") || "Fighter" });
    }
    for (const c of coaches) {
      list.push({ kind: "coach", id: c.id, name: c.name, photo_path: c.photo_path, detail: c.gym ?? c.specialties ?? "Coach" });
    }
    for (const r of referees) {
      list.push({ kind: "referee", id: r.id, name: r.name, photo_path: r.photo_path, detail: r.sanctioning_body ?? "Referee" });
    }
    for (const gm of gymManagers) {
      list.push({ kind: "gym_manager", id: gm.id, name: gm.name, photo_path: gm.photo_path, detail: gm.gym_name ?? "Gym Manager" });
    }
    return list;
  }, [fighters, coaches, referees, gymManagers]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () =>
      allProfiles.filter((p) => {
        if (!q) return true;
        return p.name.toLowerCase().includes(q) || p.detail.toLowerCase().includes(q);
      }),
    [allProfiles, q],
  );

  const onCreated = (kind: ProfileKind | "gym" | "gym_manager") =>
    async (id: string, name: string, photo_path: string | null) => {
      setCreating(null);
      if (isGymManager && myGymId && (kind === "fighter" || kind === "coach")) {
        try {
          await api.addGymMember(myGymId, id, kind);
        } catch {
          // non-fatal
        }
      }
      if (kind === "gym") {
        // no sign-in for gym entities
      } else if (kind === "gym_manager") {
        setActive({ kind: "gym_manager", id, name, photo_path });
      } else if (!isGymManager) {
        setActive({ kind, id, name, photo_path });
      }
      load();
    };

  const signIn = (p: { kind: ProfileKind; id: string; name: string; photo_path: string | null }) => {
    setActive(p);
  };

  const signOut = () => setActive(null);

  // ─── Signed-in as gym manager → show gym overview ─────────────
  if (isGymManager && active) {
    const myFighters = fighters.filter((f) => f.gym_id === myGymId);
    const myCoaches = coaches.filter((c) => c.gym_id === myGymId);

    return (
      <div className="mx-auto max-w-5xl space-y-6 px-8 py-8">
        <header className="flex items-center justify-between">
          <AlionWordmark size={36} />
          <div className="flex items-center gap-3">
            <span className="rounded-lg bg-emerald-500/10 px-2.5 py-1 text-xs text-emerald-300">
              Gym Manager: <span className="font-medium">{active.name}</span>
            </span>
            <button
              onClick={signOut}
              className="text-xs text-neutral-500 hover:text-neutral-200"
            >
              sign out
            </button>
          </div>
        </header>

        {/* Gym header card */}
        <div className="card">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold">{myGym?.name ?? "Your Gym"}</h2>
              <p className="text-sm text-neutral-500">
                {[myGym?.city, myGym?.country].filter(Boolean).join(", ") || "No location set"}
              </p>
            </div>
            <div className="flex gap-2">
              {myGym && (
                <Link
                  href={`/gyms/${myGym.id}`}
                  className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-neutral-300 hover:bg-white/[0.07]"
                >
                  Gym profile
                </Link>
              )}
              <Link
                href="/gym-dashboard"
                className="rounded-xl bg-emerald-500 px-3 py-1.5 text-sm font-medium text-black hover:bg-emerald-400"
              >
                Full Dashboard →
              </Link>
            </div>
          </div>

          {/* Quick stats */}
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-center">
              <p className="text-3xl font-bold">{myFighters.length}</p>
              <p className="text-xs text-neutral-500">Fighters</p>
            </div>
            <div className="rounded-xl border border-white/5 bg-white/[0.02] p-4 text-center">
              <p className="text-3xl font-bold">{myCoaches.length}</p>
              <p className="text-xs text-neutral-500">Coaches</p>
            </div>
          </div>
        </div>

        {/* Quick roster */}
        <div className="card">
          <div className="flex items-baseline justify-between">
            <h3 className="font-semibold">Gym Roster</h3>
            <div className="flex gap-2">
              <button
                onClick={() => setCreating("fighter")}
                className="rounded-lg bg-emerald-500/15 px-2.5 py-1 text-xs text-emerald-300 hover:bg-emerald-500/25"
              >
                + Fighter
              </button>
              <button
                onClick={() => setCreating("coach")}
                className="rounded-lg bg-blue-500/15 px-2.5 py-1 text-xs text-blue-300 hover:bg-blue-500/25"
              >
                + Coach
              </button>
            </div>
          </div>

          {myFighters.length === 0 && myCoaches.length === 0 ? (
            <p className="mt-4 text-sm text-neutral-500">
              No members yet. Add fighters and coaches to your gym.
            </p>
          ) : (
            <ul className="mt-4 space-y-2">
              {myFighters.map((f) => (
                <li key={f.id}>
                  <Link
                    href={`/fighters/${f.id}`}
                    className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 hover:border-white/15 hover:bg-white/[0.05]"
                  >
                    <ProfileAvatar name={f.name} photo_path={f.photo_path} size={36} />
                    <div className="min-w-0 flex-1">
                      <span className="font-medium">{f.name}</span>
                      <span className="ml-2 text-xs text-neutral-500">{f.stance ?? ""}</span>
                    </div>
                    <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-300">
                      fighter
                    </span>
                  </Link>
                </li>
              ))}
              {myCoaches.map((c) => (
                <li key={c.id}>
                  <Link
                    href={`/coaches/${c.id}`}
                    className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/[0.02] p-3 hover:border-white/15 hover:bg-white/[0.05]"
                  >
                    <ProfileAvatar name={c.name} photo_path={c.photo_path} size={36} />
                    <div className="min-w-0 flex-1">
                      <span className="font-medium">{c.name}</span>
                      <span className="ml-2 text-xs text-neutral-500">{c.specialties ?? ""}</span>
                    </div>
                    <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-medium text-blue-300">
                      coach
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {creating && creating !== "admin" && (
          <CreateProfileModal
            kind={creating}
            gymId={myGymId ?? undefined}
            gymCoaches={
              myGymId && creating === "fighter"
                ? myCoaches.map((c) => ({ id: c.id, name: c.name }))
                : undefined
            }
            onClose={() => setCreating(null)}
            onCreated={onCreated(creating)}
          />
        )}
      </div>
    );
  }

  // ─── Signed-in as fighter / coach / referee → personal landing ──
  if (active && !isAdmin) {
    const profileUrl =
      active.kind === "fighter"
        ? `/fighters/${active.id}`
        : active.kind === "coach"
          ? `/coaches/${active.id}`
          : active.kind === "referee"
            ? `/referees/${active.id}`
            : "/";

    return (
      <div className="mx-auto max-w-3xl space-y-6 px-8 py-12">
        <header className="flex items-center justify-between">
          <AlionWordmark size={36} />
          <button
            onClick={signOut}
            className="text-xs text-neutral-500 hover:text-neutral-200"
          >
            sign out
          </button>
        </header>

        <div className="card flex items-center gap-4">
          <ProfileAvatar name={active.name} photo_path={active.photo_path} size={64} />
          <div className="flex-1">
            <h2 className="text-xl font-bold">{active.name}</h2>
            <p className="text-sm capitalize text-neutral-500">{active.kind}</p>
          </div>
          <Link
            href={profileUrl}
            className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
          >
            Go to profile →
          </Link>
        </div>

        <p className="text-center text-xs text-neutral-600">
          Not you?{" "}
          <button onClick={signOut} className="text-neutral-400 hover:text-neutral-200 underline">
            Switch profile
          </button>
        </p>
      </div>
    );
  }

  // ─── Not signed in (or admin) → Login / profile picker ─────────
  return (
    <div className="mx-auto max-w-4xl space-y-8 px-8 py-12">
      {/* Hero */}
      <div className="text-center">
        <AlionWordmark size={48} />
        <p className="mt-3 text-sm text-neutral-400">
          Multi-modal AI coaching for combat sports
        </p>
        {health ? (
          <span className="mt-2 inline-block rounded-full bg-emerald-500/15 px-3 py-0.5 text-[11px] text-emerald-300">
            ● API healthy · schema {health.schema_version}
          </span>
        ) : (
          <span className="mt-2 inline-block rounded-full bg-amber-500/15 px-3 py-0.5 text-[11px] text-amber-300">
            ● API unreachable
          </span>
        )}
      </div>

      {err && (
        <p className="rounded-2xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">
          {err}
        </p>
      )}

      {/* Sign in header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Sign in as…</h2>
        <div className="flex items-center gap-3">
          {/* Search */}
          {allProfiles.length > 6 && (
            <div className="relative">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search profiles…"
                className="w-56 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-8 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-violet-500/40 focus:outline-none"
              />
              <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-neutral-600 text-xs">⌕</span>
            </div>
          )}
          {!isAdmin && (
            <button
              onClick={() =>
                setActive({ kind: "admin", id: "admin", name: "Admin", photo_path: null })
              }
              className="rounded-lg border border-violet-500/30 bg-violet-500/10 px-2.5 py-1 text-xs text-violet-300 hover:bg-violet-500/20"
            >
              Admin mode
            </button>
          )}
        </div>
      </div>

      {/* Profile grid */}
      {filtered.length === 0 && allProfiles.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/10 bg-white/[0.02] p-10 text-center">
          <p className="text-neutral-300">No profiles yet</p>
          <p className="mt-1 text-sm text-neutral-500">
            Create a fighter, coach, or gym manager profile to get started.
          </p>
        </div>
      ) : filtered.length === 0 ? (
        <p className="text-sm text-neutral-500">No profiles match &ldquo;{search}&rdquo;</p>
      ) : (
        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((p) => {
            const signedIn = active?.kind === p.kind && active.id === p.id;
            const kindColor =
              p.kind === "fighter"
                ? "bg-emerald-500/15 text-emerald-300"
                : p.kind === "coach"
                  ? "bg-blue-500/15 text-blue-300"
                  : p.kind === "gym_manager"
                    ? "bg-amber-500/15 text-amber-300"
                    : "bg-neutral-500/15 text-neutral-300";

            return (
              <li key={`${p.kind}-${p.id}`}>
                <button
                  onClick={() => signIn(p)}
                  className={`flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors ${
                    signedIn
                      ? "border-emerald-500/40 bg-emerald-500/5"
                      : "border-white/5 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.05]"
                  }`}
                >
                  <ProfileAvatar name={p.name} photo_path={p.photo_path} size={48} />
                  <div className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{p.name}</span>
                    <span className="block truncate text-xs text-neutral-500">{p.detail}</span>
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${kindColor}`}>
                    {p.kind === "gym_manager" ? "manager" : p.kind}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {/* Create profile */}
      <div className="flex flex-wrap items-center justify-center gap-3 border-t border-white/5 pt-6">
        <span className="text-sm text-neutral-500">New here?</span>
        <button
          onClick={() => setCreating("fighter")}
          className="rounded-xl bg-emerald-500/15 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-500/25"
        >
          Create Fighter
        </button>
        <button
          onClick={() => setCreating("coach")}
          className="rounded-xl bg-blue-500/15 px-4 py-2 text-sm text-blue-300 hover:bg-blue-500/25"
        >
          Create Coach
        </button>
        {isAdmin && (
          <>
            <button
              onClick={() => setCreating("referee")}
              className="rounded-xl bg-neutral-500/15 px-4 py-2 text-sm text-neutral-300 hover:bg-neutral-500/25"
            >
              Create Referee
            </button>
            <button
              onClick={() => setCreating("gym")}
              className="rounded-xl bg-violet-500/15 px-4 py-2 text-sm text-violet-300 hover:bg-violet-500/25"
            >
              Create Gym
            </button>
            <button
              onClick={() => setCreating("gym_manager")}
              className="rounded-xl bg-amber-500/15 px-4 py-2 text-sm text-amber-300 hover:bg-amber-500/25"
            >
              Create Gym Manager
            </button>
          </>
        )}
      </div>

      {/* Admin roster links */}
      {isAdmin && (
        <div className="card">
          <h3 className="text-sm font-semibold text-neutral-400">Admin Quick Links</h3>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href="/compare" className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/[0.07]">
              Compare backends
            </Link>
            {gyms.map((g) => (
              <Link
                key={g.id}
                href={`/gyms/${g.id}`}
                className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/[0.07]"
              >
                {g.name}
              </Link>
            ))}
          </div>
        </div>
      )}

      {creating && creating !== "admin" && (
        <CreateProfileModal
          kind={creating}
          gymId={myGymId ?? undefined}
          gymCoaches={undefined}
          onClose={() => setCreating(null)}
          onCreated={onCreated(creating)}
        />
      )}
    </div>
  );
}

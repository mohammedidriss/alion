"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  type Gym,
  type GymManager,
  type GymMembership,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface GymRow extends Gym {
  fighterCount: number;
  coachCount: number;
  isMyGym: boolean;
}

export default function GymsPage() {
  const { user } = useAuth();
  const isGymManager = user?.role === "gym_manager";

  const [gyms, setGyms] = useState<GymRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  // Create form
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newAddress, setNewAddress] = useState("");
  const [newCity, setNewCity] = useState("");
  const [newCountry, setNewCountry] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newSpecialties, setNewSpecialties] = useState("");
  const [creating, setCreating] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!isGymManager || !user) return;
    setLoading(true);
    setLoadError(null);
    try {
      const [allGyms, gms] = await Promise.all([
        api.listGyms(),
        api.listGymManagers(),
      ]);
      const me = gms.find((gm) => gm.id === user.profile_id);
      const myGymId = me?.gym_id ?? null;

      // Fetch member counts for each gym
      const memberResults = await Promise.allSettled(
        allGyms.map((g) => api.listGymMembers(g.id)),
      );

      const rows: GymRow[] = allGyms.map((g, i) => {
        const members =
          memberResults[i].status === "fulfilled"
            ? memberResults[i].value
            : [];
        return {
          ...g,
          fighterCount: members.filter((m) => m.member_type === "fighter").length,
          coachCount: members.filter((m) => m.member_type === "coach").length,
          isMyGym: g.id === myGymId,
        };
      });

      // Sort: my gym first, then alphabetical
      rows.sort((a, b) => {
        if (a.isMyGym !== b.isMyGym) return a.isMyGym ? -1 : 1;
        return a.name.localeCompare(b.name);
      });
      setGyms(rows);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to load gyms.");
    } finally {
      setLoading(false);
    }
  }, [user, isGymManager]);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () =>
      gyms.filter((g) => {
        if (!q) return true;
        return (
          g.name.toLowerCase().includes(q) ||
          (g.city ?? "").toLowerCase().includes(q) ||
          (g.country ?? "").toLowerCase().includes(q)
        );
      }),
    [gyms, q],
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setCreateError(null);
    try {
      await api.createGym({
        name: newName.trim(),
        address: newAddress || undefined,
        city: newCity || undefined,
        country: newCountry || undefined,
        phone: newPhone || undefined,
        email: newEmail || undefined,
        specialties: newSpecialties || undefined,
      });

      // Reset
      setNewName("");
      setNewAddress("");
      setNewCity("");
      setNewCountry("");
      setNewPhone("");
      setNewEmail("");
      setNewSpecialties("");
      setShowForm(false);
      load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Failed to create gym.");
    } finally {
      setCreating(false);
    }
  };

  if (!isGymManager) {
    return (
      <div className="px-8 py-12 text-neutral-400">
        Sign in as a gym manager to access this page.
      </div>
    );
  }

  if (loading) {
    return <div className="px-8 py-12 text-neutral-400">Loading gyms...</div>;
  }

  if (loadError) {
    return (
      <div className="px-8 py-12">
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {loadError}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6 px-8 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Gyms</h1>
          <p className="text-sm text-neutral-500">
            {gyms.length} gym{gyms.length !== 1 ? "s" : ""} in the network
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
        >
          {showForm ? "Cancel" : "+ Add Gym"}
        </button>
      </header>

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleCreate} className="card space-y-4">
          <h3 className="font-semibold">New Gym</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Name *</label>
              <input
                type="text"
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Gym name"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">City</label>
              <input
                type="text"
                value={newCity}
                onChange={(e) => setNewCity(e.target.value)}
                placeholder="e.g. Las Vegas"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Country</label>
              <input
                type="text"
                value={newCountry}
                onChange={(e) => setNewCountry(e.target.value)}
                placeholder="e.g. USA"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Address</label>
              <input
                type="text"
                value={newAddress}
                onChange={(e) => setNewAddress(e.target.value)}
                placeholder="Street address"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Phone</label>
              <input
                type="tel"
                value={newPhone}
                onChange={(e) => setNewPhone(e.target.value)}
                placeholder="+1 234 567 890"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Email</label>
              <input
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="info@gym.com"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-3">
              <label className="mb-1 block text-xs font-medium text-neutral-400">Specialties</label>
              <input
                type="text"
                value={newSpecialties}
                onChange={(e) => setNewSpecialties(e.target.value)}
                placeholder="e.g. Boxing, MMA, Muay Thai"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
          </div>
          {createError && (
            <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-3 py-2 text-xs text-red-300">
              {createError}
            </p>
          )}
          <button
            type="submit"
            disabled={creating || !newName.trim()}
            className="rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
          >
            {creating ? "Creating..." : "Create Gym"}
          </button>
        </form>
      )}

      {/* Search */}
      <div className="relative max-w-sm">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search gyms..."
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">⌕</span>
      </div>

      {/* Gyms grid */}
      {filtered.length === 0 ? (
        <div className="card py-8 text-center text-neutral-500">
          {gyms.length === 0
            ? "No gyms yet. Create your first gym above."
            : "No gyms match your search."}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((g) => (
            <Link
              key={g.id}
              href={`/gyms/${g.id}`}
              className={`card transition-colors hover:bg-white/[0.04] ${
                g.isMyGym ? "border-emerald-500/30" : ""
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="font-medium">{g.name}</p>
                  <p className="mt-0.5 text-xs text-neutral-500">
                    {[g.city, g.country].filter(Boolean).join(", ") || "No location"}
                  </p>
                </div>
                {g.isMyGym && (
                  <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[9px] font-medium text-emerald-300">
                    Your gym
                  </span>
                )}
              </div>

              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5 text-center">
                  <p className="text-xl font-bold">{g.fighterCount}</p>
                  <p className="text-[10px] text-neutral-500">Fighters</p>
                </div>
                <div className="rounded-lg border border-white/5 bg-white/[0.02] p-2.5 text-center">
                  <p className="text-xl font-bold">{g.coachCount}</p>
                  <p className="text-[10px] text-neutral-500">Coaches</p>
                </div>
              </div>

              {g.specialties && (
                <p className="mt-3 text-[11px] text-neutral-500">{g.specialties}</p>
              )}
              {(g.email || g.phone) && (
                <p className="mt-1.5 text-[11px] text-neutral-600">
                  {[g.email, g.phone].filter(Boolean).join(" · ")}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

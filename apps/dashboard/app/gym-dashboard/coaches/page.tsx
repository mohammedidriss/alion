"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type CoachingLevel,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";

const COACHING_LEVELS: CoachingLevel[] = ["amateur", "professional", "both"];

export default function CoachesPage() {
  const { user } = useAuth();
  const isGymManager = user?.role === "gym_manager";

  const [gymId, setGymId] = useState<string | null>(null);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");

  // Create form
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPhone, setNewPhone] = useState("");
  const [newSpecialties, setNewSpecialties] = useState("");
  const [newLevel, setNewLevel] = useState<CoachingLevel>("both");
  const [newYears, setNewYears] = useState("");
  const [newCertifications, setNewCertifications] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    if (!isGymManager || !user) return;
    setLoading(true);
    try {
      const gms = await api.listGymManagers();
      const me = gms.find((gm) => gm.id === user.profile_id);
      if (!me) return;
      setGymId(me.gym_id);
      const cs = await api.listCoaches(me.gym_id);
      setCoaches(cs);
    } finally {
      setLoading(false);
    }
  }, [user, isGymManager]);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () => coaches.filter((c) => !q || c.name.toLowerCase().includes(q)),
    [coaches, q],
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!gymId || !newName.trim()) return;
    setCreating(true);
    try {
      const created = await api.createCoach({
        name: newName.trim(),
        gym_id: gymId,
      });
      // Update additional fields
      const patch: Record<string, unknown> = {};
      if (newEmail) patch.email = newEmail;
      if (newPhone) patch.phone = newPhone;
      if (newSpecialties) patch.specialties = newSpecialties;
      if (newLevel) patch.coaching_level = newLevel;
      if (newYears) patch.years_experience = parseInt(newYears);
      if (newCertifications) patch.certifications = newCertifications;
      if (Object.keys(patch).length > 0) {
        await api.updateCoach(created.id, patch);
      }

      // Reset form
      setNewName("");
      setNewEmail("");
      setNewPhone("");
      setNewSpecialties("");
      setNewLevel("both");
      setNewYears("");
      setNewCertifications("");
      setShowForm(false);
      load();
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
    return <div className="px-8 py-12 text-neutral-400">Loading coaches...</div>;
  }

  return (
    <div className="space-y-6 px-8 py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Coaches</h1>
          <p className="text-sm text-neutral-500">
            {coaches.length} coach{coaches.length !== 1 ? "es" : ""} on staff
          </p>
        </div>
        <button
          onClick={() => setShowForm(!showForm)}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
        >
          {showForm ? "Cancel" : "+ Add Coach"}
        </button>
      </header>

      {/* Create form */}
      {showForm && (
        <form onSubmit={handleCreate} className="card space-y-4">
          <h3 className="font-semibold">New Coach</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Name *</label>
              <input
                type="text"
                required
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Coach name"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Email</label>
              <input
                type="email"
                value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                placeholder="coach@example.com"
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
              <label className="mb-1 block text-xs font-medium text-neutral-400">Specialties</label>
              <input
                type="text"
                value={newSpecialties}
                onChange={(e) => setNewSpecialties(e.target.value)}
                placeholder="e.g. Boxing, Striking, Conditioning"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Coaching Level</label>
              <select
                value={newLevel}
                onChange={(e) => setNewLevel(e.target.value as CoachingLevel)}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
              >
                {COACHING_LEVELS.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Years Experience</label>
              <input
                type="number"
                min="0"
                value={newYears}
                onChange={(e) => setNewYears(e.target.value)}
                placeholder="e.g. 10"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div className="sm:col-span-2 lg:col-span-3">
              <label className="mb-1 block text-xs font-medium text-neutral-400">Certifications</label>
              <input
                type="text"
                value={newCertifications}
                onChange={(e) => setNewCertifications(e.target.value)}
                placeholder="e.g. USA Boxing Level 3, NASM-CPT"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
          </div>
          <button
            type="submit"
            disabled={creating || !newName.trim()}
            className="rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50"
          >
            {creating ? "Creating..." : "Create Coach"}
          </button>
        </form>
      )}

      {/* Search */}
      <div className="relative max-w-sm">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search coaches..."
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">⌕</span>
      </div>

      {/* Coaches grid */}
      {filtered.length === 0 ? (
        <div className="card py-8 text-center text-neutral-500">
          {coaches.length === 0
            ? "No coaches yet. Add your first coach above."
            : "No coaches match your search."}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((c) => (
            <Link
              key={c.id}
              href={`/coaches/${c.id}`}
              className="card flex gap-3 hover:border-white/15 hover:bg-white/[0.04] transition-colors"
            >
              <ProfileAvatar name={c.name} photo_path={c.photo_path} size={48} />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{c.name}</p>
                {c.specialties && (
                  <p className="mt-0.5 text-xs text-neutral-400">{c.specialties}</p>
                )}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {c.coaching_level && (
                    <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-medium text-blue-300">
                      {c.coaching_level}
                    </span>
                  )}
                  {c.years_experience != null && (
                    <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-400">
                      {c.years_experience} yr{c.years_experience !== 1 ? "s" : ""}
                    </span>
                  )}
                  {c.certifications && (
                    <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-400">
                      certified
                    </span>
                  )}
                </div>
                {(c.email || c.phone) && (
                  <p className="mt-2 text-[11px] text-neutral-500">
                    {[c.email, c.phone].filter(Boolean).join(" · ")}
                  </p>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type Coach } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminCoachesPage() {
  const { user } = useAuth();
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listCoaches();
      setCoaches(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load coaches");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () => coaches.filter((c) => !q || c.name.toLowerCase().includes(q) || (c.gym ?? "").toLowerCase().includes(q)),
    [coaches, q],
  );

  if (user?.role !== "admin") {
    return <div className="px-8 py-12 text-neutral-400">Admin access required.</div>;
  }

  return (
    <div className="space-y-6 px-8 py-8">
      <header>
        <h1 className="text-2xl font-bold">All Coaches</h1>
        <p className="text-sm text-neutral-500">{coaches.length} coaches across all gyms</p>
      </header>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      <div className="relative max-w-sm">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search coaches..."
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">&#x2315;</span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-neutral-400">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="card py-8 text-center text-neutral-500">No coaches found.</div>
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
                {c.gym && (
                  <p className="mt-0.5 text-[11px] text-amber-300/80">
                    <span className="mr-1">🏟</span>{c.gym}
                  </p>
                )}
                {c.specialties && <p className="mt-0.5 text-xs text-neutral-400">{c.specialties}</p>}
                {/* Tags */}
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {c.coaching_level && (
                    <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] font-medium text-blue-300">{c.coaching_level}</span>
                  )}
                  {c.years_experience != null && (
                    <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-400">{c.years_experience} yrs exp</span>
                  )}
                  {c.certifications && (
                    <span className="rounded-full bg-violet-500/15 px-2 py-0.5 text-[10px] text-violet-300" title={c.certifications}>
                      {c.certifications.length > 25 ? c.certifications.slice(0, 25) + "..." : c.certifications}
                    </span>
                  )}
                </div>
                {/* Contact + license */}
                <div className="mt-1.5 space-y-0.5">
                  {(c.email || c.phone) && (
                    <p className="text-[11px] text-neutral-500">{[c.email, c.phone].filter(Boolean).join(" · ")}</p>
                  )}
                  {c.license_number && (
                    <p className="text-[10px] text-neutral-500">
                      License: {c.license_number}
                      {c.license_expiry && <span className="ml-1">(exp {new Date(c.license_expiry).toLocaleDateString()})</span>}
                    </p>
                  )}
                  {c.notable_fighters && (
                    <p className="text-[10px] text-neutral-500" title={c.notable_fighters}>
                      Trained: {c.notable_fighters.length > 40 ? c.notable_fighters.slice(0, 40) + "..." : c.notable_fighters}
                    </p>
                  )}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

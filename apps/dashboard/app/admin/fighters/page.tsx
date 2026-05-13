"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type Fighter } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminFightersPage() {
  const { user } = useAuth();
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listFighters();
      setFighters(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load fighters");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () => fighters.filter((f) => !q || f.name.toLowerCase().includes(q) || (f.nickname ?? "").toLowerCase().includes(q)),
    [fighters, q],
  );

  if (user?.role !== "admin") {
    return <div className="px-8 py-12 text-neutral-400">Admin access required.</div>;
  }

  return (
    <div className="space-y-6 px-8 py-8">
      <header>
        <h1 className="text-2xl font-bold">All Fighters</h1>
        <p className="text-sm text-neutral-500">{fighters.length} fighters across all gyms</p>
      </header>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      <div className="relative max-w-sm">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search fighters..."
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">&#x2315;</span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-neutral-400">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="card py-8 text-center text-neutral-500">No fighters found.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((f) => (
            <Link
              key={f.id}
              href={`/fighters/${f.id}`}
              className="card flex gap-3 hover:border-white/15 hover:bg-white/[0.04] transition-colors"
            >
              <ProfileAvatar name={f.name} photo_path={f.photo_path} size={48} />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{f.name}</p>
                {f.nickname && <p className="text-xs text-neutral-500">&ldquo;{f.nickname}&rdquo;</p>}
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {f.stance && (
                    <span className="rounded-full bg-white/[0.06] px-2 py-0.5 text-[10px] text-neutral-400">{f.stance}</span>
                  )}
                  {f.skill_level && (
                    <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">{f.skill_level}</span>
                  )}
                  {f.weight_class && (
                    <span className="rounded-full bg-blue-500/15 px-2 py-0.5 text-[10px] text-blue-300">{f.weight_class}</span>
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

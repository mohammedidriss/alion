"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type Gym } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminGymsPage() {
  const { user } = useAuth();
  const [gyms, setGyms] = useState<Gym[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listGyms();
      setGyms(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load gyms");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () => gyms.filter((g) => !q || g.name.toLowerCase().includes(q) || (g.city ?? "").toLowerCase().includes(q)),
    [gyms, q],
  );

  if (user?.role !== "admin") {
    return <div className="px-4 py-8 sm:px-8 sm:py-12 text-neutral-400">Admin access required.</div>;
  }

  return (
    <div className="space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      <header>
        <h1 className="text-2xl font-bold">All Gyms</h1>
        <p className="text-sm text-neutral-500">{gyms.length} gyms in the system</p>
      </header>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      <div className="relative max-w-sm">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search gyms..."
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
        />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">&#x2315;</span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-neutral-400">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="card py-8 text-center text-neutral-500">No gyms found.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((g) => (
            <Link
              key={g.id}
              href={`/gyms/${g.id}`}
              className="card transition-colors hover:border-white/15 hover:bg-white/[0.04]"
            >
              <p className="font-medium">{g.name}</p>
              <p className="mt-0.5 text-xs text-neutral-500">
                {[g.city, g.country].filter(Boolean).join(", ") || "No location"}
              </p>
              {g.specialties && <p className="mt-2 text-[11px] text-neutral-500">{g.specialties}</p>}
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

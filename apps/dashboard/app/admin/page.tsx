"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, type AdminSystemStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminDashboard() {
  const { user } = useAuth();
  const [stats, setStats] = useState<AdminSystemStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.adminStats().then(setStats).catch((e) => setError(e.message));
  }, []);

  if (user?.role !== "admin") {
    return (
      <div className="px-8 py-12 text-neutral-400">
        Admin access required.
      </div>
    );
  }

  return (
    <div className="space-y-8 px-8 py-8">
      <header>
        <h1 className="text-2xl font-bold">System Administration</h1>
        <p className="text-sm text-neutral-500">
          Full system overview and management
        </p>
      </header>

      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {error}
        </p>
      )}

      {/* Stats grid */}
      {stats && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <StatCard label="Total Users" value={stats.total_users} />
          <StatCard label="Active Users" value={stats.active_users} accent={stats.active_users < stats.total_users ? "yellow" : "green"} />
          <StatCard label="Fighters" value={stats.fighters} />
          <StatCard label="Coaches" value={stats.coaches} />
          <StatCard label="Gym Managers" value={stats.gym_managers} />
          <StatCard label="Admins" value={stats.admins} />
          <StatCard label="Gyms" value={stats.gyms} />
        </div>
      )}

      {/* Quick actions */}
      <section>
        <h2 className="mb-4 text-lg font-semibold">Quick Actions</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <ActionCard
            href="/admin/users"
            icon="◉"
            title="User Management"
            description="View, edit, deactivate users. Reset passwords. Manage roles."
          />
          <ActionCard
            href="/admin/fighters"
            icon="⊕"
            title="All Fighters"
            description="Browse all fighters across all gyms. Manage general profiles."
          />
          <ActionCard
            href="/admin/coaches"
            icon="◈"
            title="All Coaches"
            description="Browse all coaches across all gyms. Manage general profiles."
          />
          <ActionCard
            href="/admin/gyms"
            icon="⌂"
            title="All Gyms"
            description="Browse all gyms. Create, edit, delete gym records."
          />
          <ActionCard
            href="/compare"
            icon="C"
            title="Compare Backends"
            description="Compare AI backend performance and accuracy."
          />
        </div>
      </section>
    </div>
  );
}

function StatCard({ label, value, accent = "emerald" }: { label: string; value: number; accent?: string }) {
  const colors: Record<string, string> = {
    emerald: "text-emerald-400",
    yellow: "text-yellow-400",
    green: "text-emerald-400",
  };
  return (
    <div className="card text-center">
      <p className={`text-3xl font-bold ${colors[accent] ?? colors.emerald}`}>{value}</p>
      <p className="mt-1 text-xs text-neutral-500">{label}</p>
    </div>
  );
}

function ActionCard({ href, icon, title, description }: { href: string; icon: string; title: string; description: string }) {
  return (
    <Link
      href={href}
      className="card flex gap-3 transition-colors hover:border-white/15 hover:bg-white/[0.04]"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-white/[0.06] text-lg">
        {icon}
      </span>
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-xs text-neutral-500">{description}</p>
      </div>
    </Link>
  );
}

"use client";

/**
 * A physician's page (ADR-046): the fighters who chose them. Each opens on the
 * fighter's health notes; their training sessions and heart rate are one tab away.
 * A fighter adds or removes their physicians on their own Team page.
 */

import Link from "next/link";
import { useEffect, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type PhysicianFighter } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function PhysicianPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<PhysicianFighter[] | null>(null);

  useEffect(() => {
    api
      .physicianFighters()
      .then(setRows)
      .catch(() => setRows([]));
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-5 px-4 py-5 sm:px-8 sm:py-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">My fighters</h1>
        <p className="text-sm text-neutral-400">
          The fighters who chose you as their physician{user ? `, ${user.name}` : ""}. You see their health
          notes and training sessions; every look at health notes is logged.
        </p>
      </header>
      {rows === null && <p className="text-sm text-neutral-500">Loading…</p>}
      {rows && rows.length === 0 && (
        <div className="card text-sm text-neutral-300">
          No fighter has chosen you yet. A fighter adds you on their Team page with your account email
          ({user?.email}).
        </div>
      )}
      {rows && rows.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2">
          {rows.map((f) => (
            <li key={f.fighter_id} className="card flex items-center gap-3">
              <ProfileAvatar name={f.name} photo_path={f.photo_path} size={44} />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{f.name}</p>
                <p className="text-xs text-neutral-500">since {new Date(f.since).toLocaleDateString()}</p>
              </div>
              <div className="flex flex-col gap-1 text-right text-xs">
                <Link href={`/fighters/${f.fighter_id}/medical`} className="text-emerald-400 hover:underline">
                  Health notes
                </Link>
                <Link href={`/fighters/${f.fighter_id}/sessions`} className="text-neutral-300 hover:underline">
                  Sessions
                </Link>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

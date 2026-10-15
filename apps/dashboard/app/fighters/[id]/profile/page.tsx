"use client";

/**
 * A fighter's Profile tab: where their profile is edited, and deleted — for whoever
 * may edit it (their coaches, their gym's leaders, researchers, admins). The
 * dashboard only shows; a fighter edits their own profile on the profile page.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { DeleteProfileDialog } from "@/components/DeleteProfileDialog";
import { FighterEditModal } from "@/components/FighterEditModal";
import { api, type Fighter, type FighterOptions } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function label(s: string | null | undefined): string {
  return s ? s.replace(/_/g, " ") : "—";
}

export default function FighterProfileTab({ params }: { params: { id: string } }) {
  const id = params.id;
  const { user } = useAuth();
  const router = useRouter();
  const own = user?.role === "fighter" && user.profile_id === id;
  const canEdit = !!user && ((user.role !== "fighter" && user.role !== "physician") || user.is_researcher);
  const [fighter, setFighter] = useState<Fighter | null>(null);
  const [options, setOptions] = useState<FighterOptions | null>(null);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (own) router.replace("/profile"); // your own profile lives on the profile page
  }, [own, router]);

  const load = useCallback(async () => {
    try {
      const [f, o] = await Promise.all([api.getFighter(id), api.fighterOptions().catch(() => null)]);
      setFighter(f);
      setOptions(o);
    } catch (e) {
      setErr(String(e instanceof Error ? e.message : e));
    }
  }, [id]);
  useEffect(() => {
    if (!own) void load();
  }, [own, load]);

  if (own || !fighter) {
    return <div className="px-4 py-8 text-neutral-400 sm:px-8">{err ?? "Loading…"}</div>;
  }

  const record = `${fighter.record_wins ?? 0}–${fighter.record_losses ?? 0}–${fighter.record_draws ?? 0}`;
  const rows: [string, string][] = [
    ["Name", fighter.name],
    ["Nickname", fighter.nickname ?? "—"],
    ["Stance", label(fighter.stance)],
    ["Weight class", label(fighter.weight_class)],
    ["Skill level", label(fighter.skill_level)],
    ["Gym", fighter.gym ?? "—"],
    ["Record (W–L–D)", record],
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      <header>
        <h1 className="text-2xl font-semibold">Profile</h1>
        <p className="text-sm text-neutral-400">{fighter.name}&apos;s profile — edited here, not on the dashboard.</p>
      </header>
      {err && <p className="rounded-xl border border-red-500/30 bg-red-950/30 p-3 text-sm text-red-200">{err}</p>}

      <section className="card space-y-3">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 border-b border-white/5 py-1">
              <dt className="text-neutral-500">{k}</dt>
              <dd className="text-right capitalize text-neutral-200">{v}</dd>
            </div>
          ))}
        </dl>
        {canEdit ? (
          <div className="flex flex-wrap gap-2 pt-2">
            <button
              onClick={() => setEditing(true)}
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm hover:bg-white/[0.07]"
            >
              Edit profile
            </button>
            <button
              onClick={() => setDeleting(true)}
              className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/20"
            >
              Delete profile
            </button>
          </div>
        ) : (
          <p className="text-xs text-neutral-500">Only the fighter, their coaches and their gym change this profile.</p>
        )}
      </section>

      {editing && (
        <FighterEditModal
          fighter={fighter}
          options={options}
          onCancel={() => setEditing(false)}
          onSave={async (patch) => {
            try {
              await api.updateFighter(id, patch);
              setEditing(false);
              await load();
            } catch (e) {
              setErr(String(e instanceof Error ? e.message : e));
            }
          }}
        />
      )}
      {deleting && (
        <DeleteProfileDialog
          fighterId={id}
          fighterName={fighter.name}
          onCancel={() => setDeleting(false)}
          onDone={(choice) => {
            setDeleting(false);
            if (choice === "profile") router.push("/");
            else void load();
          }}
        />
      )}
    </div>
  );
}

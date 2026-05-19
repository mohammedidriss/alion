"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import {
  api,
  type Coach,
  type Fighter,
  type Gym,
  type GymManager,
  type GymMembership,
  type GymPatch,
} from "@/lib/api";
import { useAuth } from "@/lib/auth";


export default function GymDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const activeRole = user?.role ?? null;
  const isAdmin = activeRole === "admin";

  const [gym, setGym] = useState<Gym | null>(null);
  const [members, setMembers] = useState<GymMembership[]>([]);
  const [fighters, setFighters] = useState<Fighter[]>([]);
  const [coaches, setCoaches] = useState<Coach[]>([]);
  const [gymManagers, setGymManagers] = useState<GymManager[]>([]);
  const [otherGymMemberIds, setOtherGymMemberIds] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState(false);
  const [patch, setPatch] = useState<GymPatch>({});
  const [saving, setSaving] = useState(false);
  const [addType, setAddType] = useState<"fighter" | "coach">("fighter");
  const [addId, setAddId] = useState("");
  const [adding, setAdding] = useState(false);

  const load = useCallback(async () => {
    const [g, ms, fs, cs, gms, gyms] = await Promise.all([
      api.getGym(id),
      api.listGymMembers(id),
      api.listFighters(),
      api.listCoaches(),
      api.listGymManagers(),
      api.listGyms(),
    ]);
    setGym(g);
    setMembers(ms);
    setFighters(fs);
    setCoaches(cs);
    setGymManagers(gms);
    // Fetch members of all OTHER gyms to know who's taken
    const otherGyms = gyms.filter((og) => og.id !== id);
    const otherMembers = await Promise.all(
      otherGyms.map((og) => api.listGymMembers(og.id)),
    );
    const taken = new Set<string>();
    for (const list of otherMembers) {
      for (const m of list) taken.add(m.member_id);
    }
    setOtherGymMemberIds(taken);
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    try {
      const updated = await api.updateGym(id, patch);
      setGym(updated);
      setEditing(false);
      setPatch({});
    } finally {
      setSaving(false);
    }
  };

  const addMember = async () => {
    if (!addId) return;
    setAdding(true);
    try {
      await api.addGymMember(id, addId, addType);
      setAddId("");
      await load();
    } finally {
      setAdding(false);
    }
  };

  const removeMember = async (membershipId: number) => {
    await api.removeGymMember(id, membershipId);
    setMembers((prev) => prev.filter((m) => m.id !== membershipId));
  };

  const deleteGym = async () => {
    if (!confirm("Delete this gym? This cannot be undone.")) return;
    await api.deleteGym(id);
    router.push("/");
  };

  if (!gym) {
    return (
      <div className="mx-auto max-w-4xl px-8 py-12 text-neutral-400">
        Loading gym…
      </div>
    );
  }

  const memberIds = new Set(members.map((m) => m.member_id));
  // Admin, gym manager for this gym, or coach who belongs to this gym can manage members
  const isGymCoach =
    activeRole === "coach" && user?.profile_id ? memberIds.has(user.profile_id) : false;
  const isGymMgr =
    activeRole === "gym_manager" && user?.profile_id
      ? gymManagers.some((gm) => gm.id === user.profile_id && gm.gym_id === id)
      : false;
  const canManage = isAdmin || isGymCoach || isGymMgr;
  // Gym managers can only add fighters/coaches not already in another gym
  const availFighters = fighters.filter(
    (f) =>
      !memberIds.has(f.id) && (!isGymMgr || !otherGymMemberIds.has(f.id)),
  );
  const availCoaches = coaches.filter(
    (c) =>
      !memberIds.has(c.id) && (!isGymMgr || !otherGymMemberIds.has(c.id)),
  );
  const options = addType === "fighter" ? availFighters : availCoaches;

  const val = (field: keyof GymPatch) =>
    (patch[field] !== undefined ? patch[field] : gym[field]) ?? "";

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-8 py-8">
      <Link
        href="/"
        className="text-sm text-neutral-500 hover:text-neutral-300"
      >
        ← Back to roster
      </Link>

      {/* Header */}
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-violet-500/15 text-2xl font-bold text-violet-300">
            {gym.name[0]?.toUpperCase() ?? "G"}
          </div>
          <div>
            <h1 className="text-2xl font-bold">{gym.name}</h1>
            <p className="text-sm text-neutral-500">
              {[gym.city, gym.country].filter(Boolean).join(", ") || "No location set"}
            </p>
          </div>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            <button
              onClick={() => setEditing(!editing)}
              className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-1.5 text-sm text-neutral-300 hover:bg-white/[0.07]"
            >
              {editing ? "Cancel" : "Edit"}
            </button>
            <button
              onClick={deleteGym}
              className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-sm text-red-300 hover:bg-red-500/20"
            >
              Delete
            </button>
          </div>
        )}
      </header>

      {/* Edit form */}
      {editing && (
        <div className="card space-y-3">
          <h2 className="text-sm font-semibold text-neutral-400 uppercase tracking-wider">
            Edit gym
          </h2>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {(
              [
                ["name", "Name"],
                ["address", "Address"],
                ["city", "City"],
                ["country", "Country"],
                ["phone", "Phone"],
                ["email", "Email"],
                ["specialties", "Specialties"],
              ] as const
            ).map(([key, label]) => (
              <div key={key}>
                <label className="text-xs text-neutral-500">{label}</label>
                <input
                  value={val(key)}
                  onChange={(e) => setPatch({ ...patch, [key]: e.target.value })}
                  className="mt-1 w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm focus:border-violet-500/50 focus:outline-none"
                />
              </div>
            ))}
          </div>
          <button
            onClick={save}
            disabled={saving}
            className="rounded-xl bg-emerald-500 px-4 py-1.5 text-sm font-medium text-black hover:bg-emerald-400 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      )}

      {/* Info card */}
      {!editing && (
        <div className="card">
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
            {[
              ["Address", gym.address],
              ["City", gym.city],
              ["Country", gym.country],
              ["Phone", gym.phone],
              ["Email", gym.email],
              ["Specialties", gym.specialties],
            ].map(([label, value]) => (
              <div key={label}>
                <span className="text-xs text-neutral-500">{label}</span>
                <p className="text-neutral-200">{value || "—"}</p>
              </div>
            ))}
          </div>
          {gym.notes && (
            <p className="mt-3 text-sm text-neutral-400">{gym.notes}</p>
          )}
        </div>
      )}

      {/* Members */}
      <section className="card">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold">
            Members{" "}
            <span className="text-sm font-normal text-neutral-500">
              ({members.length})
            </span>
          </h2>
        </div>

        {members.length === 0 ? (
          <p className="mt-3 text-sm text-neutral-500">
            No members yet. Add fighters and coaches below.
          </p>
        ) : (
          <ul className="mt-3 space-y-2">
            {members.map((m) => (
              <li
                key={m.id}
                className="flex items-center justify-between rounded-xl border border-white/5 bg-white/[0.02] p-3"
              >
                <div className="flex items-center gap-3">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      m.member_type === "fighter"
                        ? "bg-emerald-500/15 text-emerald-300"
                        : "bg-blue-500/15 text-blue-300"
                    }`}
                  >
                    {m.member_type}
                  </span>
                  <Link
                    href={`/${m.member_type === "fighter" ? "fighters" : "coaches"}/${m.member_id}`}
                    className="text-sm font-medium hover:text-violet-300"
                  >
                    {m.member_name || m.member_id.slice(0, 8)}
                  </Link>
                  {m.joined_on && (
                    <span className="text-xs text-neutral-600">
                      joined {new Date(m.joined_on).toLocaleDateString()}
                    </span>
                  )}
                </div>
                {canManage && (
                  <button
                    onClick={() => removeMember(m.id)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    remove
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        {/* Add member */}
        {canManage && (
          <div className="mt-4 flex flex-wrap items-end gap-3 border-t border-white/5 pt-4">
            <div>
              <label className="text-xs text-neutral-500">Type</label>
              <select
                value={addType}
                onChange={(e) => {
                  setAddType(e.target.value as "fighter" | "coach");
                  setAddId("");
                }}
                className="mt-1 block w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
              >
                <option value="fighter">Fighter</option>
                <option value="coach">Coach</option>
              </select>
            </div>
            <div className="flex-1 min-w-[180px]">
              <label className="text-xs text-neutral-500">
                Select {addType}
              </label>
              <select
                value={addId}
                onChange={(e) => setAddId(e.target.value)}
                className="mt-1 block w-full rounded-xl border border-white/5 bg-black/30 px-3 py-2 text-sm"
              >
                <option value="">— choose —</option>
                {options.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>
            <button
              onClick={addMember}
              disabled={!addId || adding}
              className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400 disabled:cursor-not-allowed disabled:bg-neutral-700 disabled:text-neutral-400"
            >
              {adding ? "Adding…" : "+ Add member"}
            </button>
          </div>
        )}
      </section>
    </div>
  );
}

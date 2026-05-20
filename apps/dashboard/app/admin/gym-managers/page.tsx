"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api, type AuthUser, type Gym, type GymManager } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function AdminGymManagersPage() {
  const { user: me } = useAuth();
  const [managers, setManagers] = useState<GymManager[]>([]);
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [gyms, setGyms] = useState<Gym[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Create form
  const [showCreate, setShowCreate] = useState(false);
  const [cName, setCName] = useState("");
  const [cEmail, setCEmail] = useState("");
  const [cPhone, setCPhone] = useState("");
  const [cGymId, setCGymId] = useState("");
  const [creating, setCreating] = useState(false);
  const [createErr, setCreateErr] = useState<string | null>(null);

  // Edit state
  const [editId, setEditId] = useState<string | null>(null);
  const [eName, setEName] = useState("");
  const [eEmail, setEEmail] = useState("");
  const [ePhone, setEPhone] = useState("");
  const [saving, setSaving] = useState(false);

  // Link state
  const [linkId, setLinkId] = useState<string | null>(null);
  const [linkUserId, setLinkUserId] = useState("");
  const [linking, setLinking] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [mgrs, us, gs] = await Promise.all([
        api.listGymManagers(),
        api.adminListUsers(),
        api.listGyms(),
      ]);
      setManagers(mgrs);
      setUsers(us);
      setGyms(gs);
      if (!cGymId && gs.length > 0) setCGymId(gs[0].id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [cGymId]);

  useEffect(() => { load(); }, [load]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build lookup: profile_id -> user email
  const profileToUser = useMemo(() => {
    const m: Record<string, AuthUser> = {};
    for (const u of users) {
      if (u.profile_id) m[u.profile_id] = u;
    }
    return m;
  }, [users]);

  // Unlinked gym_manager users (role=gym_manager, no profile_id yet)
  const unlinkableUsers = useMemo(
    () => users.filter((u) => u.role === "gym_manager" && !u.profile_id),
    [users],
  );

  const q = search.toLowerCase().trim();
  const filtered = useMemo(
    () => managers.filter((m) => !q || m.name.toLowerCase().includes(q) || m.gym_name.toLowerCase().includes(q)),
    [managers, q],
  );

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!cName.trim() || !cGymId) return;
    setCreating(true);
    setCreateErr(null);
    try {
      await api.createGymManager({ name: cName.trim(), gym_id: cGymId, email: cEmail || undefined, phone: cPhone || undefined });
      setMsg("Gym manager profile created.");
      setCName(""); setCEmail(""); setCPhone("");
      setShowCreate(false);
      load();
    } catch (err) {
      setCreateErr(err instanceof Error ? err.message : "Failed to create");
    } finally {
      setCreating(false);
    }
  };

  const handleEditSave = async (mgr: GymManager) => {
    setSaving(true);
    try {
      await api.updateGymManager(mgr.id, { name: eName || mgr.name, email: eEmail || undefined, phone: ePhone || undefined });
      setMsg("Updated.");
      setEditId(null);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (mgr: GymManager) => {
    if (!confirm(`Delete gym manager "${mgr.name}"? This cannot be undone.`)) return;
    try {
      await api.deleteGymManager(mgr.id);
      setMsg(`Deleted ${mgr.name}.`);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleLink = async (mgr: GymManager) => {
    if (!linkUserId) return;
    setLinking(true);
    try {
      await api.adminUpdateUser(linkUserId, { profile_id: mgr.id });
      setMsg(`Linked ${mgr.name} to user account.`);
      setLinkId(null);
      setLinkUserId("");
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Link failed");
    } finally {
      setLinking(false);
    }
  };

  if (me?.role !== "admin") {
    return <div className="px-4 py-8 text-neutral-400">Admin access required.</div>;
  }

  return (
    <div className="space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Gym Managers</h1>
          <p className="text-sm text-neutral-500">{managers.length} profiles</p>
        </div>
        <button
          onClick={() => setShowCreate(!showCreate)}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
        >
          {showCreate ? "Cancel" : "+ New Gym Manager"}
        </button>
      </header>

      {msg && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-950/30 px-4 py-2 text-sm text-emerald-300">
          {msg}
          <button onClick={() => setMsg(null)} className="text-xs hover:text-white">dismiss</button>
        </div>
      )}
      {error && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">{error}</p>
      )}

      {/* Create form */}
      {showCreate && (
        <form onSubmit={handleCreate} className="card space-y-4">
          <h3 className="font-semibold">New Gym Manager Profile</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Name *</label>
              <input required value={cName} onChange={(e) => setCName(e.target.value)} placeholder="Full name"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Gym *</label>
              <select required value={cGymId} onChange={(e) => setCGymId(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-[#0d0d12] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none">
                {gyms.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Email</label>
              <input type="email" value={cEmail} onChange={(e) => setCEmail(e.target.value)} placeholder="manager@gym.com"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Phone</label>
              <input type="tel" value={cPhone} onChange={(e) => setCPhone(e.target.value)} placeholder="+1 234 567 890"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
            </div>
          </div>
          {createErr && <p className="text-xs text-red-400">{createErr}</p>}
          <button type="submit" disabled={creating || !cName.trim() || !cGymId}
            className="rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50">
            {creating ? "Creating..." : "Create Profile"}
          </button>
        </form>
      )}

      {/* Search */}
      <div className="relative max-w-sm">
        <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name or gym..."
          className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
        <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">&#x2315;</span>
      </div>

      {loading ? (
        <div className="py-12 text-center text-neutral-400">Loading...</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/5">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 bg-white/[0.02] text-left text-xs text-neutral-500">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Gym</th>
                <th className="hidden sm:table-cell px-4 py-3">Email</th>
                <th className="hidden md:table-cell px-4 py-3">Phone</th>
                <th className="px-4 py-3">Linked User</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((mgr) => {
                const linkedUser = profileToUser[mgr.id];
                const isEditing = editId === mgr.id;
                const isLinking = linkId === mgr.id;
                return (
                  <tr key={mgr.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="px-4 py-3 font-medium">
                      {isEditing ? (
                        <input value={eName} onChange={(e) => setEName(e.target.value)}
                          className="w-32 rounded-lg border border-white/10 bg-white/[0.05] px-2 py-1 text-sm text-neutral-200 focus:outline-none" />
                      ) : mgr.name}
                    </td>
                    <td className="px-4 py-3 text-neutral-400">{mgr.gym_name}</td>
                    <td className="hidden sm:table-cell px-4 py-3 text-neutral-400">
                      {isEditing ? (
                        <input type="email" value={eEmail} onChange={(e) => setEEmail(e.target.value)} placeholder={mgr.email ?? ""}
                          className="w-40 rounded-lg border border-white/10 bg-white/[0.05] px-2 py-1 text-sm text-neutral-200 focus:outline-none" />
                      ) : (mgr.email ?? <span className="text-neutral-600">—</span>)}
                    </td>
                    <td className="hidden md:table-cell px-4 py-3 text-neutral-400">
                      {isEditing ? (
                        <input type="tel" value={ePhone} onChange={(e) => setEPhone(e.target.value)} placeholder={mgr.phone ?? ""}
                          className="w-32 rounded-lg border border-white/10 bg-white/[0.05] px-2 py-1 text-sm text-neutral-200 focus:outline-none" />
                      ) : (mgr.phone ?? <span className="text-neutral-600">—</span>)}
                    </td>
                    <td className="px-4 py-3">
                      {isLinking ? (
                        <div className="flex items-center gap-2">
                          <select value={linkUserId} onChange={(e) => setLinkUserId(e.target.value)}
                            className="rounded-lg border border-white/10 bg-[#0d0d12] px-2 py-1 text-xs text-neutral-200 focus:outline-none">
                            <option value="">— select user —</option>
                            {unlinkableUsers.map((u) => <option key={u.id} value={u.id}>{u.email}</option>)}
                          </select>
                          <button onClick={() => handleLink(mgr)} disabled={!linkUserId || linking}
                            className="rounded-lg bg-emerald-500 px-2 py-1 text-xs font-medium text-black hover:bg-emerald-400 disabled:opacity-50">
                            {linking ? "…" : "Link"}
                          </button>
                          <button onClick={() => { setLinkId(null); setLinkUserId(""); }} className="text-xs text-neutral-500 hover:text-white">✕</button>
                        </div>
                      ) : linkedUser ? (
                        <span className="text-xs text-emerald-400">{linkedUser.email}</span>
                      ) : (
                        <span className="text-xs text-neutral-600">unlinked</span>
                      )}
                    </td>
                    <td className="px-2 py-3 sm:px-4">
                      <div className="flex justify-end gap-1">
                        {isEditing ? (
                          <>
                            <button onClick={() => handleEditSave(mgr)} disabled={saving}
                              className="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-medium text-black hover:bg-emerald-400 disabled:opacity-50">
                              {saving ? "…" : "Save"}
                            </button>
                            <button onClick={() => setEditId(null)} className="rounded-lg border border-white/10 px-3 py-1.5 text-xs text-neutral-300 hover:bg-white/[0.04]">
                              Cancel
                            </button>
                          </>
                        ) : (
                          <>
                            <button onClick={() => { setEditId(mgr.id); setEName(mgr.name); setEEmail(mgr.email ?? ""); setEPhone(mgr.phone ?? ""); }}
                              className="rounded-lg p-2 text-xs text-neutral-400 hover:bg-white/[0.06] hover:text-white" title="Edit">
                              <span className="hidden sm:inline">Edit</span><span className="sm:hidden">✏️</span>
                            </button>
                            {!linkedUser && (
                              <button onClick={() => { setLinkId(mgr.id); setLinkUserId(""); }}
                                className="rounded-lg p-2 text-xs text-blue-400/70 hover:bg-blue-500/10 hover:text-blue-300" title="Link to user account">
                                <span className="hidden sm:inline">Link User</span><span className="sm:hidden">🔗</span>
                              </button>
                            )}
                            <button onClick={() => handleDelete(mgr)}
                              className="rounded-lg p-2 text-xs text-red-400/70 hover:bg-red-500/10 hover:text-red-300" title="Delete">
                              <span className="hidden sm:inline">Delete</span><span className="sm:hidden">🗑</span>
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="py-8 text-center text-neutral-500">
              {managers.length === 0 ? "No gym manager profiles yet. Create one above." : "No results match your search."}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

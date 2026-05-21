"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ProfileAvatar } from "@/components/ProfileAvatar";
import { api, type AuthUser, type UnifiedPerson, type UserRole } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ROLES: UserRole[] = ["fighter", "coach", "referee", "gym_manager", "admin"];

export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<UnifiedPerson[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState<UserRole | "all">("all");

  // Modal state
  const [editUser, setEditUser] = useState<UnifiedPerson | null>(null);
  const [resetUser, setResetUser] = useState<UnifiedPerson | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [editName, setEditName] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editRole, setEditRole] = useState<UserRole>("fighter");
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [actionErr, setActionErr] = useState<string | null>(null);

  // Create user form
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [newUserName, setNewUserName] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState<UserRole>("fighter");
  const [creatingUser, setCreatingUser] = useState(false);
  const [createUserErr, setCreateUserErr] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.adminListEveryone();
      setUsers(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const q = search.toLowerCase().trim();
  const filtered = useMemo(() => {
    return users.filter((u) => {
      if (roleFilter !== "all" && u.role !== roleFilter) return false;
      if (!q) return true;
      return u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q);
    });
  }, [users, q, roleFilter]);

  const handleResetPassword = async () => {
    if (!resetUser || !newPassword) return;
    if (!resetUser.user_id) { setActionErr("This person has no login account to reset."); return; }
    setActionErr(null);
    try {
      const res = await api.adminResetPassword(resetUser.user_id, newPassword);
      setActionMsg(res.message);
      setResetUser(null);
      setNewPassword("");
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Failed to reset password");
    }
  };

  const handleToggleActive = async (u: UnifiedPerson) => {
    if (!u.user_id) { setActionErr("This person has no login account to activate/deactivate."); return; }
    setActionErr(null);
    try {
      if (u.is_active) {
        await api.adminDeactivateUser(u.user_id);
        setActionMsg(`Deactivated ${u.email}`);
      } else {
        await api.adminActivateUser(u.user_id);
        setActionMsg(`Activated ${u.email}`);
      }
      load();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Action failed");
    }
  };

  const handleEditSave = async () => {
    if (!editUser || !editUser.user_id) {
      setActionErr("This person has no login account to edit.");
      setEditUser(null);
      return;
    }
    setActionErr(null);
    try {
      const fields: Record<string, unknown> = {};
      if (editName && editName !== editUser.name) fields.name = editName;
      if (editEmail && editEmail !== editUser.email) fields.email = editEmail;
      if (editRole !== editUser.role) fields.role = editRole;
      if (Object.keys(fields).length === 0) { setEditUser(null); return; }
      await api.adminUpdateUser(editUser.user_id, fields as Partial<Pick<AuthUser, "name" | "email" | "role">>);
      setActionMsg(`Updated ${editUser.email}`);
      setEditUser(null);
      load();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Update failed");
    }
  };

  const handleCreateUser = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingUser(true);
    setCreateUserErr(null);
    try {
      await api.adminCreateUser({ name: newUserName.trim(), email: newUserEmail.trim(), password: newUserPassword, role: newUserRole });
      setActionMsg(`Created user ${newUserEmail}`);
      setNewUserName(""); setNewUserEmail(""); setNewUserPassword(""); setNewUserRole("fighter");
      setShowCreateUser(false);
      load();
    } catch (e) {
      setCreateUserErr(e instanceof Error ? e.message : "Failed to create user");
    } finally {
      setCreatingUser(false);
    }
  };

  const handleDelete = async (u: UnifiedPerson) => {
    if (!u.user_id) { setActionErr("This person has no login account to delete."); return; }
    setActionErr(null);
    try {
      await api.adminDeleteUser(u.user_id);
      setActionMsg(`Deleted ${u.email}`);
      load();
    } catch (e) {
      setActionErr(e instanceof Error ? e.message : "Delete failed");
    }
  };

  if (me?.role !== "admin") {
    return <div className="px-4 py-8 sm:px-8 sm:py-12 text-neutral-400">Admin access required.</div>;
  }

  return (
    <div className="space-y-6 px-4 py-6 sm:px-8 sm:py-8">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">User Management</h1>
          <p className="text-sm text-neutral-500">{users.length} users in system</p>
        </div>
        <button
          onClick={() => setShowCreateUser(!showCreateUser)}
          className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400"
        >
          {showCreateUser ? "Cancel" : "+ Create User"}
        </button>
      </header>

      {/* Create User form */}
      {showCreateUser && (
        <form onSubmit={handleCreateUser} className="card space-y-4">
          <h3 className="font-semibold">New User Account</h3>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Name *</label>
              <input required value={newUserName} onChange={(e) => setNewUserName(e.target.value)} placeholder="Full name"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Email *</label>
              <input required type="email" value={newUserEmail} onChange={(e) => setNewUserEmail(e.target.value)} placeholder="user@example.com"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Password *</label>
              <input required type="password" value={newUserPassword} onChange={(e) => setNewUserPassword(e.target.value)} placeholder="Min 6 characters"
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Role *</label>
              <select required value={newUserRole} onChange={(e) => setNewUserRole(e.target.value as UserRole)}
                className="w-full rounded-xl border border-white/10 bg-[#0d0d12] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none">
                {ROLES.map((r) => <option key={r} value={r}>{r.replace("_", " ")}</option>)}
              </select>
            </div>
          </div>
          {createUserErr && <p className="text-xs text-red-400">{createUserErr}</p>}
          <button type="submit" disabled={creatingUser || !newUserName.trim() || !newUserEmail.trim() || newUserPassword.length < 6}
            className="rounded-xl bg-emerald-500 px-6 py-2.5 text-sm font-semibold text-black hover:bg-emerald-400 disabled:opacity-50">
            {creatingUser ? "Creating..." : "Create User"}
          </button>
        </form>
      )}

      {/* Notifications */}
      {actionMsg && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-950/30 px-4 py-2 text-sm text-emerald-300">
          {actionMsg}
          <button onClick={() => setActionMsg(null)} className="text-xs hover:text-white">dismiss</button>
        </div>
      )}
      {(error || actionErr) && (
        <p className="rounded-lg border border-red-500/30 bg-red-950/30 px-4 py-3 text-sm text-red-300">
          {error || actionErr}
        </p>
      )}

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 max-w-sm">
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by name or email..."
            className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 pl-9 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
          />
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-neutral-600 text-sm">&#x2315;</span>
        </div>
        <select
          value={roleFilter}
          onChange={(e) => setRoleFilter(e.target.value as UserRole | "all")}
          className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
        >
          <option value="all">All roles</option>
          {ROLES.map((r) => (
            <option key={r} value={r}>{r.replace("_", " ")}</option>
          ))}
        </select>
      </div>

      {/* Reset Password Modal */}
      {resetUser && (
        <div className="card border-amber-500/30 bg-amber-950/10">
          <h3 className="font-semibold">Reset Password for {resetUser.email}</h3>
          <div className="mt-3 flex gap-3">
            <input
              type="text"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="New password (min 6 chars)"
              className="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-emerald-500/40 focus:outline-none"
            />
            <button
              onClick={handleResetPassword}
              disabled={newPassword.length < 6}
              className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-medium text-black hover:bg-amber-400 disabled:opacity-50"
            >
              Reset
            </button>
            <button
              onClick={() => { setResetUser(null); setNewPassword(""); }}
              className="rounded-xl border border-white/10 px-4 py-2 text-sm text-neutral-300 hover:bg-white/[0.04]"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {editUser && (
        <div className="card border-blue-500/30 bg-blue-950/10">
          <h3 className="font-semibold">Edit User: {editUser.email}</h3>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Name</label>
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Email</label>
              <input
                type="email"
                value={editEmail}
                onChange={(e) => setEditEmail(e.target.value)}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-400">Role</label>
              <select
                value={editRole}
                onChange={(e) => setEditRole(e.target.value as UserRole)}
                className="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-neutral-200 focus:border-emerald-500/40 focus:outline-none"
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>{r.replace("_", " ")}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={handleEditSave} className="rounded-xl bg-emerald-500 px-4 py-2 text-sm font-medium text-black hover:bg-emerald-400">
              Save Changes
            </button>
            <button onClick={() => setEditUser(null)} className="rounded-xl border border-white/10 px-4 py-2 text-sm text-neutral-300 hover:bg-white/[0.04]">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Users table */}
      {loading ? (
        <div className="py-12 text-center text-neutral-400">Loading users...</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-white/5">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/5 bg-white/[0.02] text-left text-xs text-neutral-500">
                <th className="px-4 py-3">Name</th>
                <th className="hidden sm:table-cell px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Login</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <ProfileAvatar name={u.name} photo_path={u.photo_path} size={28} />
                      <span className="font-medium">{u.name}</span>
                    </div>
                  </td>
                  <td className="hidden sm:table-cell px-4 py-3 text-neutral-400">{u.email ?? "—"}</td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      u.role === "admin" ? "bg-purple-500/15 text-purple-300" :
                      u.role === "gym_manager" ? "bg-blue-500/15 text-blue-300" :
                      u.role === "coach" ? "bg-amber-500/15 text-amber-300" :
                      u.role === "fighter" ? "bg-emerald-500/15 text-emerald-300" :
                      "bg-white/[0.06] text-neutral-400"
                    }`}>
                      {u.role.replace("_", " ")}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      u.has_account ? "bg-emerald-500/15 text-emerald-300" : "bg-neutral-500/15 text-neutral-400"
                    }`}>
                      {u.has_account ? "✓ account" : "no login"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      u.is_active ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"
                    }`}>
                      {u.is_active ? "active" : "disabled"}
                    </span>
                  </td>
                  <td className="px-2 py-3 sm:px-4">
                    <div className="flex justify-end gap-1">
                      <button
                        onClick={() => { setEditUser(u); setEditName(u.name); setEditEmail(u.email ?? ""); setEditRole(u.role); }}
                        className="rounded-lg p-2 text-xs text-neutral-400 hover:bg-white/[0.06] hover:text-white"
                        title="Edit user"
                      >
                        <span className="hidden sm:inline">Edit</span>
                        <span className="sm:hidden">✏️</span>
                      </button>
                      <button
                        onClick={() => setResetUser(u)}
                        className="rounded-lg p-2 text-xs text-amber-400/70 hover:bg-amber-500/10 hover:text-amber-300"
                        title="Reset password"
                      >
                        <span className="hidden sm:inline">Reset PW</span>
                        <span className="sm:hidden">🔑</span>
                      </button>
                      <button
                        onClick={() => handleToggleActive(u)}
                        disabled={u.user_id === me?.id}
                        className={`rounded-lg p-2 text-xs disabled:opacity-30 ${
                          u.is_active
                            ? "text-yellow-400/70 hover:bg-yellow-500/10 hover:text-yellow-300"
                            : "text-emerald-400/70 hover:bg-emerald-500/10 hover:text-emerald-300"
                        }`}
                        title={u.is_active ? "Deactivate" : "Activate"}
                      >
                        <span className="hidden sm:inline">{u.is_active ? "Disable" : "Enable"}</span>
                        <span className="sm:hidden">{u.is_active ? "⏸" : "▶"}</span>
                      </button>
                      <button
                        onClick={() => { if (confirm(`Delete user ${u.email ?? u.name}? This cannot be undone.`)) handleDelete(u); }}
                        disabled={u.user_id === me?.id}
                        className="rounded-lg p-2 text-xs text-red-400/70 hover:bg-red-500/10 hover:text-red-300 disabled:opacity-30"
                        title="Delete user"
                      >
                        <span className="hidden sm:inline">Delete</span>
                        <span className="sm:hidden">🗑</span>
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="py-8 text-center text-neutral-500">No users match your filters.</div>
          )}
        </div>
      )}
    </div>
  );
}

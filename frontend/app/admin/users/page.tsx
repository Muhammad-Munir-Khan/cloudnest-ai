"use client";

import { useEffect, useMemo, useState } from "react";
import {
  MoreVertical,
  Pencil,
  KeyRound,
  Ban,
  CheckCircle2,
  LogOut,
  Trash2,
  Search,
  ArrowUpDown,
} from "lucide-react";

import {
  adminListUsers,
  adminSetUserRole,
  adminSetUserActive,
  adminEditUser,
  adminSendReset,
  adminForceLogout,
  adminDeleteUser,
} from "@/lib/api";
import type { AdminUserInfo } from "@/lib/types";
import { useAuth } from "@/components/AuthProvider";

const ROLES = ["user", "corpus_admin", "super_admin"];

type SortKey = "email" | "role" | "status" | "created_at";
type SortDir = "asc" | "desc";

export default function AdminUsersPage() {
  const { user: me } = useAuth();
  const myId = (me as { id?: string } | null)?.id ?? "";

  const [users, setUsers] = useState<AdminUserInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);

  // search + sort state
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("created_at");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  // edit modal state
  const [editing, setEditing] = useState<AdminUserInfo | null>(null);
  const [editName, setEditName] = useState("");

  // confirm modal for force-logout
  const [confirmLogout, setConfirmLogout] = useState<AdminUserInfo | null>(null);

  // confirm modal for block (with optional reason). Unblock is one-click.
  const [confirmBlock, setConfirmBlock] = useState<AdminUserInfo | null>(null);
  const [blockReason, setBlockReason] = useState("");

  // confirm modal for HARD DELETE. Type-to-confirm: the typed text must match
  // the target user's email exactly before the Delete button enables.
  const [confirmDelete, setConfirmDelete] = useState<AdminUserInfo | null>(null);
  const [deleteEmailConfirm, setDeleteEmailConfirm] = useState("");

  const load = () => {
    adminListUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"));
  };
  useEffect(load, []);

  const flash = (msg: string) => {
    setNotice(msg);
    setError(null);
    setTimeout(() => setNotice(null), 4000);
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const rows = q
      ? users.filter(
          (u) =>
            u.email.toLowerCase().includes(q) ||
            (u.display_name?.toLowerCase().includes(q) ?? false),
        )
      : [...users];

    rows.sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      switch (sortKey) {
        case "email":
          return a.email.localeCompare(b.email) * dir;
        case "role":
          return a.role.localeCompare(b.role) * dir;
        case "status":
          return (Number(a.is_active) - Number(b.is_active)) * dir;
        case "created_at": {
          const aT = a.created_at ? new Date(a.created_at).getTime() : 0;
          const bT = b.created_at ? new Date(b.created_at).getTime() : 0;
          return (aT - bT) * dir;
        }
      }
    });
    return rows;
  }, [users, query, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const changeRole = async (id: string, role: string) => {
    setBusyId(id);
    setError(null);
    try {
      const updated = await adminSetUserRole(id, role);
      setUsers((p) => p.map((u) => (u.id === id ? updated : u)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyId(null);
    }
  };

  const toggleActive = async (id: string, next: boolean, reason?: string) => {
    setBusyId(id);
    setError(null);
    setMenuId(null);
    try {
      const updated = await adminSetUserActive(id, next, reason);
      setUsers((p) => p.map((u) => (u.id === id ? updated : u)));
      flash(next ? "User unblocked. They have been emailed." : "User blocked and signed out. They have been emailed.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyId(null);
    }
  };

  const doBlock = async () => {
    if (!confirmBlock) return;
    await toggleActive(confirmBlock.id, false, blockReason);
    setConfirmBlock(null);
    setBlockReason("");
  };

  const doDelete = async () => {
    if (!confirmDelete) return;
    // Defensive: refuse to proceed if typed email doesn't match exactly.
    // The button is also disabled below, but defense-in-depth never hurts.
    if (deleteEmailConfirm.trim() !== confirmDelete.email) {
      setError("Typed email does not match. Aborted.");
      return;
    }
    const targetEmail = confirmDelete.email;
    const targetId = confirmDelete.id;
    setBusyId(targetId);
    setError(null);
    setMenuId(null);
    try {
      await adminDeleteUser(targetId);
      setUsers((prev) => prev.filter((u) => u.id !== targetId));
      flash(`User ${targetEmail} deleted permanently. They have been emailed.`);
      setConfirmDelete(null);
      setDeleteEmailConfirm("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed");
    } finally {
      setBusyId(null);
    }
  };

  const openEdit = (u: AdminUserInfo) => {
    setEditing(u);
    setEditName(u.display_name || "");
    setMenuId(null);
  };

  const saveEdit = async () => {
    if (!editing) return;
    setBusyId(editing.id);
    setError(null);
    try {
      const updated = await adminEditUser(editing.id, editName || null);
      setUsers((p) => p.map((u) => (u.id === editing.id ? updated : u)));
      setEditing(null);
      flash("Details updated.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyId(null);
    }
  };

  const sendReset = async (u: AdminUserInfo) => {
    setBusyId(u.id);
    setError(null);
    setMenuId(null);
    try {
      await adminSendReset(u.id);
      flash(`Password reset link sent to ${u.email}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyId(null);
    }
  };

  const doForceLogout = async () => {
    if (!confirmLogout) return;
    setBusyId(confirmLogout.id);
    setError(null);
    try {
      await adminForceLogout(confirmLogout.id);
      flash(`${confirmLogout.email} has been force-logged-out.`);
      setConfirmLogout(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    } finally {
      setBusyId(null);
    }
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso;
    }
  };

  return (
    <div onClick={() => setMenuId(null)}>
      <h1 className="text-2xl font-semibold text-[var(--fg-primary)]">Users</h1>
      <p className="text-sm text-[var(--fg-secondary)] mt-1">
        Manage roles and access. {users.length} total.
      </p>

      {error && (
        <div className="mt-6 px-4 py-3 rounded-lg border border-red-500/30 bg-red-500/10 text-sm text-red-400">
          {error}
        </div>
      )}
      {notice && (
        <div className="mt-6 px-4 py-3 rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-sm text-emerald-400">
          {notice}
        </div>
      )}

      {/* Search bar */}
      <div className="mt-6 relative">
        <Search
          size={14}
          className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--fg-tertiary)]"
        />
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search by email or name…"
          className="w-full pl-9 pr-3 py-2 text-sm bg-[var(--bg-card)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:outline-none focus:border-[var(--accent)] transition-colors"
        />
      </div>

      <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] overflow-visible">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[var(--border-subtle)] text-left">
              <SortableHeader
                label="Email"
                active={sortKey === "email"}
                dir={sortDir}
                onClick={() => toggleSort("email")}
              />
              <SortableHeader
                label="Role"
                active={sortKey === "role"}
                dir={sortDir}
                onClick={() => toggleSort("role")}
              />
              <SortableHeader
                label="Status"
                active={sortKey === "status"}
                dir={sortDir}
                onClick={() => toggleSort("status")}
              />
              <SortableHeader
                label="Signed up"
                active={sortKey === "created_at"}
                dir={sortDir}
                onClick={() => toggleSort("created_at")}
              />
              <th className="px-4 py-3 text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)] text-right">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => {
              const isMe = u.id === myId;
              return (
                <tr
                  key={u.id}
                  className="border-b border-[var(--border-subtle)] last:border-0"
                >
                  <td className="px-4 py-3 text-[var(--fg-primary)]">
                    {u.email}
                    {isMe && (
                      <span className="ml-2 px-1.5 py-0.5 text-[0.6rem] font-mono uppercase tracking-wider text-[var(--accent)] bg-[var(--accent)]/10 rounded">
                        you
                      </span>
                    )}
                    {u.display_name && (
                      <div className="text-[0.7rem] text-[var(--fg-tertiary)]">
                        {u.display_name}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      value={u.role}
                      disabled={busyId === u.id || isMe}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => changeRole(u.id, e.target.value)}
                      className="bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-md px-2 py-1 text-[var(--fg-primary)] text-sm focus:outline-none focus:border-[var(--accent)] disabled:opacity-50"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2.5 py-1 rounded-md text-xs font-medium ${
                        u.is_active
                          ? "bg-emerald-500/10 text-emerald-400"
                          : "bg-red-500/10 text-red-400"
                      }`}
                    >
                      {u.is_active ? "active" : "blocked"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-[var(--fg-secondary)] text-xs">
                    {formatDate(u.created_at)}
                  </td>
                  <td className="px-4 py-3 text-right relative">
                    <button
                      disabled={busyId === u.id}
                      onClick={(e) => {
                        e.stopPropagation();
                        setMenuId(menuId === u.id ? null : u.id);
                      }}
                      className="p-1.5 rounded-md hover:bg-[var(--bg-base)] text-[var(--fg-secondary)] disabled:opacity-40"
                    >
                      <MoreVertical size={16} />
                    </button>

                    {menuId === u.id && (
                      <div
                        onClick={(e) => e.stopPropagation()}
                        className="absolute right-4 top-12 z-20 w-56 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-card)] shadow-xl py-1"
                      >
                        <MenuItem
                          icon={<Pencil size={14} />}
                          label="Edit details"
                          onClick={() => openEdit(u)}
                        />
                        <MenuItem
                          icon={<KeyRound size={14} />}
                          label="Send reset link"
                          onClick={() => sendReset(u)}
                        />
                        {u.is_active ? (
                          <MenuItem
                            icon={<Ban size={14} />}
                            label="Block user"
                            danger
                            disabled={isMe}
                            onClick={() => {
                              setConfirmBlock(u);
                              setBlockReason("");
                              setMenuId(null);
                            }}
                          />
                        ) : (
                          <MenuItem
                            icon={<CheckCircle2 size={14} />}
                            label="Unblock user"
                            onClick={() => toggleActive(u.id, true)}
                          />
                        )}
                        <div className="my-1 border-t border-[var(--border-subtle)]" />
                        <MenuItem
                          icon={<Trash2 size={14} />}
                          label="Delete user"
                          danger
                          disabled={isMe}
                          onClick={() => {
                            setConfirmDelete(u);
                            setDeleteEmailConfirm("");
                            setMenuId(null);
                          }}
                        />
                        <MenuItem
                          icon={<LogOut size={14} />}
                          label="Force logout"
                          danger
                          disabled={isMe}
                          onClick={() => {
                            setConfirmLogout(u);
                            setMenuId(null);
                          }}
                        />
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td
                  colSpan={5}
                  className="px-4 py-8 text-center text-sm text-[var(--fg-tertiary)]"
                >
                  No users match &ldquo;{query}&rdquo;.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Edit modal */}
      {editing && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => setEditing(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="text-lg font-semibold text-[var(--fg-primary)]">
              Edit user
            </h2>
            <p className="text-xs text-[var(--fg-tertiary)] mt-1">
              {editing.email}
            </p>

            <label className="block mt-5">
              <span className="text-xs font-medium text-[var(--fg-secondary)] uppercase tracking-wider">
                Display name
              </span>
              <input
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                placeholder="(none)"
                className="mt-2 w-full px-3 py-2 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] focus:outline-none focus:border-[var(--accent)]"
              />
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setEditing(null)}
                className="px-4 py-2 rounded-lg text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-base)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={saveEdit}
                disabled={busyId === editing.id}
                className="px-4 py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50 transition-opacity"
              >
                {busyId === editing.id ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Hard delete confirmation with type-to-confirm gate */}
      {confirmDelete && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
          onClick={() =>
            busyId !== confirmDelete.id && (setConfirmDelete(null), setDeleteEmailConfirm(""))
          }
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-red-500/30 bg-[var(--bg-card)] p-6"
          >
            <div className="flex items-center gap-2 mb-1">
              <Trash2 size={18} className="text-red-500" />
              <h2 className="text-lg font-semibold text-[var(--fg-primary)]">
                Delete user permanently?
              </h2>
            </div>
            <p className="text-sm text-[var(--fg-secondary)] mt-3">
              You are about to permanently delete{" "}
              <span className="text-[var(--fg-primary)] font-medium">
                {confirmDelete.email}
              </span>
              . This will remove:
            </p>
            <ul className="mt-2 text-xs text-[var(--fg-secondary)] list-disc pl-5 space-y-0.5">
              <li>Their account and login credentials</li>
              <li>All their chat sessions and messages</li>
              <li>All documents they uploaded</li>
              <li>All vector data derived from those documents</li>
            </ul>

            <div className="mt-4 p-3 rounded-lg bg-red-500/5 border border-red-500/20 text-xs text-red-400">
              This is permanent and cannot be undone.
            </div>

            <label className="block mt-5">
              <span className="text-xs font-medium text-[var(--fg-secondary)] uppercase tracking-wider">
                To confirm, type the user&apos;s email exactly
              </span>
              <input
                type="text"
                value={deleteEmailConfirm}
                onChange={(e) => setDeleteEmailConfirm(e.target.value)}
                autoFocus
                placeholder={confirmDelete.email}
                className="mt-2 w-full px-3 py-2 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:outline-none focus:border-red-500 font-mono"
              />
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => {
                  setConfirmDelete(null);
                  setDeleteEmailConfirm("");
                }}
                disabled={busyId === confirmDelete.id}
                className="px-4 py-2 rounded-lg text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-base)] transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={doDelete}
                disabled={
                  busyId === confirmDelete.id ||
                  deleteEmailConfirm.trim() !== confirmDelete.email
                }
                className="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                {busyId === confirmDelete.id
                  ? "Deleting…"
                  : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Block confirmation with optional reason */}
      {confirmBlock && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => busyId !== confirmBlock.id && setConfirmBlock(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="text-lg font-semibold text-[var(--fg-primary)]">
              Block user?
            </h2>
            <p className="text-sm text-[var(--fg-secondary)] mt-2">
              This blocks{" "}
              <span className="text-[var(--fg-primary)] font-medium">
                {confirmBlock.email}
              </span>{" "}
              and signs them out immediately. They will be emailed about
              this. Optionally, add a reason — the reason will be
              included in the email.
            </p>

            <label className="block mt-5">
              <span className="text-xs font-medium text-[var(--fg-secondary)] uppercase tracking-wider">
                Reason (optional)
              </span>
              <textarea
                value={blockReason}
                onChange={(e) => setBlockReason(e.target.value)}
                rows={3}
                maxLength={500}
                placeholder="e.g. Terms of Service violation"
                className="mt-2 w-full px-3 py-2 text-sm bg-[var(--bg-base)] border border-[var(--border-subtle)] rounded-lg text-[var(--fg-primary)] placeholder-[var(--fg-muted)] focus:outline-none focus:border-[var(--accent)] resize-none"
              />
              <span className="block text-[0.65rem] text-[var(--fg-muted)] mt-1">
                Shown to the user in the suspension email. {blockReason.length}/500
              </span>
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => {
                  setConfirmBlock(null);
                  setBlockReason("");
                }}
                disabled={busyId === confirmBlock.id}
                className="px-4 py-2 rounded-lg text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-base)] transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={doBlock}
                disabled={busyId === confirmBlock.id}
                className="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {busyId === confirmBlock.id ? "Blocking…" : "Block user"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Force-logout confirmation */}
      {confirmLogout && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 px-4"
          onClick={() => setConfirmLogout(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-card)] p-6"
          >
            <h2 className="text-lg font-semibold text-[var(--fg-primary)]">
              Force logout?
            </h2>
            <p className="text-sm text-[var(--fg-secondary)] mt-2">
              This invalidates every active session for{" "}
              <span className="text-[var(--fg-primary)] font-medium">
                {confirmLogout.email}
              </span>
              . They will need to log in again. Their account is not blocked.
            </p>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setConfirmLogout(null)}
                className="px-4 py-2 rounded-lg text-sm text-[var(--fg-secondary)] hover:bg-[var(--bg-base)] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={doForceLogout}
                disabled={busyId === confirmLogout.id}
                className="px-4 py-2 rounded-lg bg-red-500 text-white text-sm font-medium hover:bg-red-600 disabled:opacity-50 transition-colors"
              >
                {busyId === confirmLogout.id ? "Logging out…" : "Force logout"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function SortableHeader({
  label,
  active,
  dir,
  onClick,
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
}) {
  return (
    <th
      onClick={onClick}
      className="px-4 py-3 text-[0.65rem] font-mono uppercase tracking-wider text-[var(--fg-tertiary)] cursor-pointer select-none hover:text-[var(--fg-secondary)] transition-colors"
    >
      <span className="inline-flex items-center gap-1.5">
        {label}
        <ArrowUpDown
          size={11}
          className={
            active
              ? `text-[var(--accent)] ${dir === "asc" ? "rotate-180" : ""}`
              : "text-[var(--fg-muted)]"
          }
        />
      </span>
    </th>
  );
}

function MenuItem({
  icon,
  label,
  onClick,
  danger,
  disabled,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  danger?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
        danger
          ? "text-red-400 hover:bg-red-500/10 disabled:hover:bg-transparent"
          : "text-[var(--fg-primary)] hover:bg-[var(--bg-base)] disabled:hover:bg-transparent"
      }`}
    >
      {icon}
      {label}
    </button>
  );
}
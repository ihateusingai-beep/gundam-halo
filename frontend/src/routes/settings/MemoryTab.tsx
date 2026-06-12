import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";
import type { MemoryEntry } from "@/types/api";

function formatTimestamp(epoch: number): string {
  if (!epoch) return "—";
  try {
    const d = new Date(epoch * 1000);
    return d.toLocaleString();
  } catch {
    return String(epoch);
  }
}

/** Memory tab — list all users, expand to see their memory entries, delete the wrong ones. */
export function MemoryTab() {
  const [users, setUsers] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);

  const refreshUsers = async () => {
    try {
      setError(null);
      setLoadingUsers(true);
      const data = await api.listMemoryUsers();
      setUsers(data.users);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
    } finally {
      setLoadingUsers(false);
    }
  };

  const refreshEntries = async (user: string) => {
    try {
      setError(null);
      setLoadingEntries(true);
      const data = await api.listMemoryEntries(user);
      setEntries(data.entries);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
      setEntries([]);
    } finally {
      setLoadingEntries(false);
    }
  };

  useEffect(() => {
    refreshUsers();
  }, []);

  useEffect(() => {
    if (selected) {
      refreshEntries(selected);
    } else {
      setEntries([]);
    }
  }, [selected]);

  const handleDelete = async (user: string, key: string) => {
    const ok = window.confirm(
      `Delete memory[${key}] for user "${user}"? This cannot be undone.`,
    );
    if (!ok) return;
    setDeletingKey(key);
    try {
      await api.deleteMemoryEntry(user, key);
      toast.success("Memory entry deleted", {
        description: `${user} / ${key}`,
      });
      await refreshEntries(user);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to delete", { description: msg });
    } finally {
      setDeletingKey(null);
    }
  };

  if (loadingUsers) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading users…</p>
        </div>
      </HudCard>
    );
  }

  if (error && users.length === 0) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  return (
    <div className="space-y-4">
      <HudCard>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
            User Memory
          </h3>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            M7-Phase-2.5 · read-only viewer
          </span>
        </div>

        <p className="text-xs text-[var(--text-muted)] font-mono mb-4">
          The agent's per-user key/value memory (M7-Phase-2). When the agent
          learns a fact about you (preferred name, timezone, favorite Gundam,
          …) it appears here. Auto-injected into the system prompt on every
          turn. You can{" "}
          <span className="text-[var(--danger)]">delete</span> an entry the
          agent got wrong — the next turn will not see it. The dashboard
          never writes new entries; the agent does that via{" "}
          <code>memory_write</code>.
        </p>

        {users.length === 0 ? (
          <div className="p-4 border border-dashed border-[var(--border-color)] text-center">
            <p className="text-xs text-[var(--text-muted)] font-mono">
              No users yet. Start a conversation — when the agent calls{" "}
              <code>memory_write</code>, you'll see the user here.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {users.map((u) => (
              <button
                key={u}
                onClick={() => setSelected(u)}
                className={`px-3 py-2 text-xs font-[Rajdhani] uppercase tracking-wider border transition-colors ${
                  selected === u
                    ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)]"
                    : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                }`}
              >
                {u}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 mt-4 pt-4 border-t border-[var(--border-color)]">
          <button
            onClick={refreshUsers}
            className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
          >
            Refresh
          </button>
        </div>
      </HudCard>

      {selected && (
        <HudCard>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
              {selected}
            </h4>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              {loadingEntries
                ? "loading…"
                : `${entries.length} ${entries.length === 1 ? "entry" : "entries"}`}
            </span>
          </div>

          {loadingEntries ? (
            <div className="flex items-center gap-3">
              <div className="gundam-radar w-6 h-6" />
              <p className="text-xs text-[var(--text-muted)] font-mono">
                Loading entries…
              </p>
            </div>
          ) : entries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] font-mono">
              No entries yet for this user.
            </p>
          ) : (
            <div className="space-y-2">
              {entries.map((e) => (
                <div
                  key={e.key}
                  className="border border-[var(--border-color)] bg-[var(--bg-elevated)] p-3"
                >
                  <div className="flex items-center justify-between mb-1 gap-2">
                    <code className="text-[11px] text-[var(--accent)] font-mono break-all">
                      {e.key}
                    </code>
                    <button
                      onClick={() => handleDelete(selected, e.key)}
                      disabled={deletingKey === e.key}
                      className="px-2 py-0.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 shrink-0"
                    >
                      {deletingKey === e.key ? "…" : "Delete"}
                    </button>
                  </div>
                  <p className="text-xs text-[var(--text)] font-mono whitespace-pre-wrap break-words">
                    {e.value}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] font-mono mt-2">
                    updated {formatTimestamp(e.updated_at)} · created{" "}
                    {formatTimestamp(e.created_at)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </HudCard>
      )}
    </div>
  );
}

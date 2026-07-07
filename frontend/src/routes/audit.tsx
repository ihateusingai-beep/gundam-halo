import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Reticle } from "@/components/gundam/Reticle";
import { StatusDot } from "@/components/gundam/StatusDot";
import { api, ApiError } from "@/lib/api";
import {
  backendErrorAction,
  backendErrorMessage,
  classifyBackendError,
} from "@/lib/backend-error";
import type { AuditEntry } from "@/types/api";

/** Audit log dashboard (B7).
 *
 *  Route: /audit
 *
 *  Full-screen viewer for the security audit log. Replaces the
 *  117-line quick-view inside the SecurityTab settings panel.
 *
 *  Features:
 *    - 4 stat cards (Total / Today / Blocked / Unique Actions)
 *    - Filter chips: All + per event_type
 *    - Optional target search (substring on `data.target`)
 *    - Date-bucket grouping (Today / Yesterday / This Week / Earlier)
 *    - Click entry → expand full `data` JSON
 *    - Manual refresh button (auto-refresh can be a v2)
 *
 *  The audit log is append-only NDJSON at
 *  `~/.gundam-halo/logs/audit.log`, written by AuditLogger
 *  (backend/app/security/audit.py). It subscribes to the 4
 *  MAC_OP_* event types from the EventBus — so the dashboard is
 *  scoped to **Mac control operations** (file I/O, shell, etc.),
 *  not the full event taxonomy. Other event types are visible on
 *  the live ActivityTicker instead.
 */
export function AuditDashboardPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string>("all");
  const [targetQuery, setTargetQuery] = useState<string>("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.getAuditLog(500);
      setEntries(data);
    } catch (e) {
      const kind = classifyBackendError(e);
      const { headline, hint, detail } = backendErrorMessage(kind, e);
      const fullMessage = detail
        ? `${headline} ${hint} (Server: ${detail})`
        : `${headline} ${hint}`;
      setError(fullMessage);
      const action = backendErrorAction(kind);
      toast.error("Failed to load audit log", {
        description: fullMessage,
        action: action
          ? {
              label: action.label,
              onClick: action.onClick,
            }
          : undefined,
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  // Apply filters
  const filtered = useMemo(() => {
    const byType = filterType === "all"
      ? entries
      : entries.filter((e) => e.event_type === filterType);
    if (!targetQuery.trim()) return byType;
    const q = targetQuery.toLowerCase();
    return byType.filter((e) => {
      const tgt = String(e.data?.target ?? "").toLowerCase();
      return tgt.includes(q);
    });
  }, [entries, filterType, targetQuery]);

  // Stats — computed from the unfiltered list so the header
  // always reflects the actual log, not the current filter.
  const stats = useMemo(() => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayCount = entries.filter((e) => new Date(e.ts) >= todayStart).length;
    const blockedCount = entries.filter((e) => e.event_type.includes("blocked")).length;
    const uniqueActions = new Set(
      entries.map((e) => String(e.data?.action ?? e.event_type)),
    );
    return {
      total: entries.length,
      today: todayCount,
      blocked: blockedCount,
      uniqueActions: uniqueActions.size,
    };
  }, [entries]);

  // Group by date bucket (same shape as memory.tsx)
  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  // Event types present in the log (for the filter chips)
  const eventTypes = useMemo(
    () => Array.from(new Set(entries.map((e) => e.event_type))).sort(),
    [entries],
  );

  const toggle = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <div className="flex flex-col h-full gap-3">
      <Header stats={stats} loading={loading} onRefresh={refresh} />

      {/* Filters bar */}
      <HudCard>
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-1 text-[10px] font-mono">
            <span className="text-[var(--text-muted)] uppercase tracking-wider mr-1 self-center">
              type:
            </span>
            {["all", ...eventTypes].map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={`px-2 py-0.5 rounded border transition-colors ${
                  filterType === t
                    ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)]"
                    : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)]"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-wider">
              target:
            </span>
            <input
              type="text"
              value={targetQuery}
              onChange={(e) => setTargetQuery(e.target.value)}
              placeholder="substring match on data.target"
              className="px-2 py-1 text-[10px] font-mono bg-[var(--bg-input)] border border-[var(--border-color)] rounded text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] w-56"
            />
            {targetQuery && (
              <button
                onClick={() => setTargetQuery("")}
                className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--accent)]"
                title="Clear"
              >
                ✕
              </button>
            )}
          </div>
        </div>
      </HudCard>

      {/* Log timeline */}
      <HudCard className="flex-1 overflow-y-auto">
        {loading && entries.length === 0 ? (
          <div className="flex items-center gap-3">
            <div className="gundam-radar w-6 h-6" />
            <p className="text-[var(--text-muted)] font-mono text-sm">
              Reading audit log…
            </p>
          </div>
        ) : error ? (
          <p className="text-[var(--danger)] font-mono text-sm">⚠ {error}</p>
        ) : entries.length === 0 ? (
          <Reticle>
            <h3 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
              NO AUDIT TRAIL
            </h3>
            <p className="text-sm text-[var(--text-secondary)]">
              Mac control operations (file I/O, shell, AppleScript) will be
              logged here as the agent runs.
            </p>
          </Reticle>
        ) : filtered.length === 0 ? (
          <p className="text-[var(--text-muted)] text-xs font-mono">
            // no entries match current filters
          </p>
        ) : (
          <div className="gundam-timeline">
            {groups.map(([groupName, items]) => (
              <div key={groupName}>
                <div className="gundam-timeline-group-header">
                  {groupName}{" "}
                  <span className="opacity-60">· {items.length}</span>
                </div>
                {items.map((e) => (
                  <AuditNode
                    key={e.id}
                    entry={e}
                    isOpen={!!expanded[e.id]}
                    onToggle={() => toggle(e.id)}
                  />
                ))}
              </div>
            ))}
          </div>
        )}
      </HudCard>
    </div>
  );
}

function AuditNode({
  entry,
  isOpen,
  onToggle,
}: {
  entry: AuditEntry;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const action = String(entry.data?.action ?? "");
  const target = String(entry.data?.target ?? "");
  const isBlocked = entry.event_type.includes("blocked");
  const isEnd = entry.event_type === "mac_op_end";

  // Color hint per category
  const accent = isBlocked
    ? "var(--danger)"
    : isEnd
    ? "var(--success)"
    : "var(--text-primary)";

  return (
    <div className="gundam-timeline-node">
      <div
        className={`gundam-memory-card ${isOpen ? "gundam-memory-card-expanded" : ""} cursor-pointer`}
        onClick={onToggle}
        style={{ color: accent }}
      >
        <div className="flex items-center justify-between gap-3 flex-wrap font-mono text-[10px]">
          <div className="flex items-center gap-3 min-w-0 flex-1">
            <span className="text-[var(--accent)] uppercase tracking-wider font-[Orbitron] shrink-0">
              {formatTime(entry.ts)}
            </span>
            <span className="text-[var(--text-muted)] shrink-0 uppercase tracking-wider font-bold">
              {entry.event_type}
            </span>
            {action && (
              <span className="text-[var(--text-secondary)] shrink-0">
                {action}
              </span>
            )}
            {target && (
              <span
                className="opacity-90 truncate"
                title={target}
              >
                {target}
              </span>
            )}
          </div>
          <div className="flex items-center gap-3 text-[var(--text-muted)] shrink-0">
            {entry.data?.exit_code !== undefined && (
              <span
                className={
                  Number(entry.data.exit_code) === 0
                    ? "text-[var(--success)]"
                    : "text-[var(--danger)]"
                }
              >
                exit {String(entry.data.exit_code)}
              </span>
            )}
            {entry.data?.bytes !== undefined && (
              <span>{formatBytes(Number(entry.data.bytes))}</span>
            )}
            {entry.data?.duration_ms !== undefined && (
              <span>{formatMs(Number(entry.data.duration_ms))}</span>
            )}
            <span className="text-[var(--accent)]">▶</span>
          </div>
        </div>

        {/* Expanded full data */}
        {isOpen && (
          <div className="mt-2 pt-2 border-t border-[var(--border-color)] text-[10px] font-mono">
            <DataTable data={entry.data} />
            <div className="mt-2 text-[var(--text-muted)] opacity-70">
              id: {entry.id} · ts: {entry.ts}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function DataTable({ data }: { data: Record<string, any> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <div className="text-[var(--text-muted)]">(no data)</div>;
  }
  return (
    <table className="w-full border-collapse">
      <tbody>
        {entries.map(([k, v]) => (
          <tr key={k} className="align-top">
            <td className="text-[var(--text-muted)] pr-3 py-0.5 whitespace-nowrap">
              {k}
            </td>
            <td className="text-[var(--text-primary)] py-0.5 break-all">
              {typeof v === "object" && v !== null
                ? JSON.stringify(v)
                : String(v)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Header({
  stats,
  loading,
  onRefresh,
}: {
  stats: { total: number; today: number; blocked: number; uniqueActions: number };
  loading: boolean;
  onRefresh: () => void;
}) {
  return (
    <HudCard>
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-[10px] font-mono text-[var(--text-muted)] uppercase tracking-widest mb-1">
            <Link
              to="/settings"
              className="hover:text-[var(--accent)] transition-colors"
            >
              ← Settings / Security
            </Link>
          </div>
          <h2 className="text-2xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase gundam-text-neon">
            Audit Log
          </h2>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
            Mac control operations — file I/O, shell, policy blocks
          </p>
        </div>
        <div className="flex items-center gap-2">
          <StatusDot
            status={loading ? "warn" : "ok"}
            label={loading ? "LOADING" : "LIVE"}
          />
          <button
            onClick={onRefresh}
            disabled={loading}
            className="px-3 py-1 text-[10px] font-mono uppercase tracking-wider border border-[var(--border-color)] text-[var(--text-secondary)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-50"
            title="Reload audit log from disk"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      {/* Stat cards */}
      <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
        <StatCard label="TOTAL" value={stats.total} />
        <StatCard label="TODAY" value={stats.today} accent />
        <StatCard
          label="BLOCKED"
          value={stats.blocked}
          danger={stats.blocked > 0}
        />
        <StatCard label="UNIQUE ACTIONS" value={stats.uniqueActions} />
      </div>
    </HudCard>
  );
}

function StatCard({
  label,
  value,
  accent,
  danger,
}: {
  label: string;
  value: number;
  accent?: boolean;
  danger?: boolean;
}) {
  const color = danger
    ? "var(--danger)"
    : accent
    ? "var(--accent)"
    : "var(--text-primary)";
  return (
    <div className="gundam-stat-card">
      <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
        {label}
      </div>
      <div
        className="text-2xl font-[Orbitron] tracking-wider"
        style={{ color }}
      >
        {value}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function groupByDate(
  entries: AuditEntry[],
): Array<[string, AuditEntry[]]> {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const weekAgo = new Date(today);
  weekAgo.setDate(weekAgo.getDate() - 7);

  const buckets: Record<string, AuditEntry[]> = {
    Today: [],
    Yesterday: [],
    "This Week": [],
    Earlier: [],
  };

  for (const e of entries) {
    const d = new Date(e.ts);
    if (d >= today) buckets.Today.push(e);
    else if (d >= yesterday) buckets.Yesterday.push(e);
    else if (d >= weekAgo) buckets["This Week"].push(e);
    else buckets.Earlier.push(e);
  }

  for (const k of Object.keys(buckets)) {
    buckets[k].sort((a, b) => b.ts.localeCompare(a.ts));
  }
  return Object.entries(buckets).filter(([_, v]) => v.length > 0);
}

function formatTime(iso: string): string {
  if (!iso) return "(unknown)";
  try {
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso.slice(0, 19).replace("T", " ");
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    const mon = d.toLocaleString("en", { month: "short" });
    return `${day} ${mon} ${hh}:${mm}:${ss}`;
  } catch {
    return iso;
  }
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatMs(n: number): string {
  if (n < 1000) return `${n}ms`;
  return `${(n / 1000).toFixed(2)}s`;
}

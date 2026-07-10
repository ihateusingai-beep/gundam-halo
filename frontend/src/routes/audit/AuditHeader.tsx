/**
 * AuditHeader — top of the /audit page: title, status dot, refresh
 * button, and 4 stat cards (TOTAL / TODAY / BLOCKED / UNIQUE).
 *
 * Sprint 61 R-A1: extracted from `routes/audit.tsx`. Pure
 * presentation; the orchestrator owns the data + refresh
 * callback.
 *
 * ## Props
 *
 *   - `stats` — the 4 stat values from the orchestrator's
 *     `useMemo` (computed from the unfiltered entries).
 *   - `loading` — drives the StatusDot color + Refresh button
 *     disabled state.
 *   - `onRefresh` — fired by the Refresh button. The
 *     orchestrator re-fetches `api.getAuditLog(500)`.
 */
import { Link } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";
import { StatusDot } from "@/components/gundam/StatusDot";

export interface AuditStats {
  total: number;
  today: number;
  blocked: number;
  uniqueActions: number;
}

export interface AuditHeaderProps {
  stats: AuditStats;
  loading: boolean;
  onRefresh: () => void;
}

export function AuditHeader({ stats, loading, onRefresh }: AuditHeaderProps) {
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
            data-testid="audit-refresh-button"
          >
            ↻ Refresh
          </button>
        </div>
      </div>

      <div
        className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2"
        data-testid="audit-stat-cards"
      >
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

/** Tiny inline stat card used by AuditHeader. */
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
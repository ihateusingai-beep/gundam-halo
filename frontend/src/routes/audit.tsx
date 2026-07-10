/**
 * AuditDashboardPage — orchestrator for the /audit route.
 *
 * Sprint 61 R-A1: refactored from a 482-LoC monolith into:
 *   - this orchestrator (state + composition)
 *   - `audit/format.ts` (4 pure helpers)
 *   - `audit/DataTable.tsx` (JSON detail table)
 *   - `audit/AuditNode.tsx` (single-entry expand/collapse)
 *   - `audit/AuditHeader.tsx` (title + stat cards)
 *   - `audit/AuditFilters.tsx` (type chips + target input)
 *   - `audit/AuditList.tsx` (timeline list w/ 4 render states)
 *
 * Route: /audit. Full-screen viewer for the security audit
 * log. Replaces the 117-line quick-view inside the SecurityTab
 * settings panel (B7).
 *
 * ## Features
 *
 *   - 4 stat cards (Total / Today / Blocked / Unique Actions)
 *   - Filter chips: All + per event_type
 *   - Optional target search (substring on `data.target`)
 *   - Date-bucket grouping (Today / Yesterday / This Week /
 *     Earlier) — same shape as `routes/projects/[id]/memory.tsx`
 *   - Click entry → expand full `data` JSON
 *   - Manual refresh button (auto-refresh deferred to a
 *     future sprint; the user can also navigate away + back
 *     to re-fetch, per Sprint 61 R-A4 TanStack Query upgrade
 *     coming in this sprint too)
 *
 * ## Why a single-file orchestrator
 *
 *   The orchestrator owns the cross-section state (entries,
 *   filter state, expanded map). The 5 sub-components are
 *   pure and individually testable. Sprint 61 R-A1 was the
 *   refactor; the rest of the file's behaviour is unchanged.
 */
import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";
import {
  backendErrorAction,
  backendErrorMessage,
  classifyBackendError,
} from "@/lib/backend-error";
import type { AuditEntry } from "@/types/api";

import { AuditFilters } from "./audit/AuditFilters";
import { AuditHeader, type AuditStats } from "./audit/AuditHeader";
import { AuditList } from "./audit/AuditList";
import { groupByDate } from "./audit/format";

export function AuditDashboardPage() {
  const [filterType, setFilterType] = useState<string>("all");
  const [targetQuery, setTargetQuery] = useState<string>("");
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  // Sprint 61 R-A4: TanStack Query. The previous useEffect
  // re-fetched on every mount; useQuery caches per `queryKey`
  // and dedupes rapid remounts (mobile tab switch, HMR, etc.).
  // `staleTime: 30s` is set at the QueryClient level (App.tsx)
  // so the first mount fetches, the second mount within 30s
  // reads cache. `refetchOnWindowFocus: true` keeps the log
  // fresh if the user tabs away + back.
  const { data, isLoading, error, refetch } = useQuery<AuditEntry[]>({
    queryKey: ["audit", "log", { limit: 500 }],
    queryFn: () => api.getAuditLog(500),
  });
  const entries = data ?? [];
  const loading = isLoading;
  const errorMessage =
    error != null
      ? (() => {
          const kind = classifyBackendError(error);
          const { headline, hint, detail } = backendErrorMessage(kind, error);
          return detail
            ? `${headline} ${hint} (Server: ${detail})`
            : `${headline} ${hint}`;
        })()
      : null;

  // Manual refresh — exposed via the AuditHeader's button.
  // The QueryClient's refetchOnWindowFocus handles automatic
  // freshness; this is the explicit user-triggered path.
  const refresh = () => {
    refetch().catch((e) => {
      // useQuery surfaces errors via the `error` field; this
      // catch is only for the imperative refetch promise
      // (rare — usually already handled by useQuery).
      const kind = classifyBackendError(e);
      const { headline, hint } = backendErrorMessage(kind, e);
      const action = backendErrorAction(kind);
      toast.error("Failed to load audit log", {
        description: `${headline} ${hint}`,
        action: action
          ? { label: action.label, onClick: action.onClick }
          : undefined,
      });
    });
  };

  // Apply filters
  const filtered = useMemo(() => {
    const byType =
      filterType === "all"
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
  const stats: AuditStats = useMemo(() => {
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const todayCount = entries.filter(
      (e) => new Date(e.ts) >= todayStart,
    ).length;
    const blockedCount = entries.filter((e) =>
      e.event_type.includes("blocked"),
    ).length;
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

  const groups = useMemo(() => groupByDate(filtered), [filtered]);

  const eventTypes = useMemo(
    () => Array.from(new Set(entries.map((e) => e.event_type))).sort(),
    [entries],
  );

  const toggle = (id: string) =>
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));

  return (
    <div className="flex flex-col h-full gap-3">
      <AuditHeader stats={stats} loading={loading} onRefresh={refresh} />
      <AuditFilters
        eventTypes={eventTypes}
        filterType={filterType}
        setFilterType={setFilterType}
        targetQuery={targetQuery}
        setTargetQuery={setTargetQuery}
      />
      <AuditList
        loading={loading}
        error={errorMessage}
        unfilteredCount={entries.length}
        filteredCount={filtered.length}
        groups={groups}
        expanded={expanded}
        onToggle={toggle}
      />
    </div>
  );
}
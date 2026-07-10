/**
 * AuditList — the timeline list of audit entries.
 *
 * Sprint 61 R-A1: extracted from `routes/audit.tsx`. Owns the
 * 4 list-rendering states (loading / error / empty / no-matches
 * / data). The orchestrator owns the data + expanded map.
 *
 * ## Props
 *
 *   - `loading` — drives the "Reading audit log…" placeholder.
 *   - `error` — drives the danger-text error state.
 *   - `unfilteredCount` — when 0, shows the "NO AUDIT TRAIL"
 *     reticle. This is the count BEFORE filter is applied
 *     (so the reticle shows even if the user filtered
 *     everything out — matches the orchestrator's "stats
 *     reflect the actual log, not the filter" convention).
 *   - `filteredCount` — when 0 but `unfilteredCount > 0`,
 *     shows the "no entries match current filters" hint.
 *   - `groups` — the date-bucketed output of
 *     `groupByDate(filtered)`.
 *   - `expanded: Record<string, boolean>` — expand/collapse
 *     map keyed by entry id.
 *   - `onToggle: (id: string) => void` — fired when an
 *     `AuditNode` row is clicked.
 */
import { Card } from "@/components/ui/card";
import { Reticle } from "@/components/gundam/Reticle";
import type { AuditEntry } from "@/types/api";

import { AuditNode } from "./AuditNode";
import type { DateBucket } from "./format";

export interface AuditListProps {
  loading: boolean;
  error: string | null;
  unfilteredCount: number;
  filteredCount: number;
  groups: Array<[DateBucket, AuditEntry[]]>;
  expanded: Record<string, boolean>;
  onToggle: (id: string) => void;
}

export function AuditList({
  loading,
  error,
  unfilteredCount,
  filteredCount,
  groups,
  expanded,
  onToggle,
}: AuditListProps) {
  return (
    <Card className="flex-1 overflow-y-auto" data-testid="audit-list">
      {loading && unfilteredCount === 0 ? (
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-6 h-6" />
          <p className="text-[var(--text-muted)] font-mono text-sm">
            Reading audit log…
          </p>
        </div>
      ) : error ? (
        <p className="text-[var(--danger)] font-mono text-sm">⚠ {error}</p>
      ) : unfilteredCount === 0 ? (
        <Reticle>
          <h3 className="text-lg font-[Orbitron] text-[var(--accent)] tracking-widest uppercase mb-2">
            NO AUDIT TRAIL
          </h3>
          <p className="text-sm text-[var(--text-secondary)]">
            Mac control operations (file I/O, shell, AppleScript) will be
            logged here as the agent runs.
          </p>
        </Reticle>
      ) : filteredCount === 0 ? (
        <p className="text-[var(--text-muted)] text-xs font-mono">
          // no entries match current filters
        </p>
      ) : (
        <div className="gundam-timeline">
          {groups.map(([groupName, items]) => (
            <div key={groupName}>
              <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)] mb-1 mt-2 first:mt-0">
                {groupName}
              </div>
              {items.map((entry) => (
                <AuditNode
                  key={entry.id}
                  entry={entry}
                  isOpen={!!expanded[entry.id]}
                  onToggle={() => onToggle(entry.id)}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}
/**
 * AuditNode — single audit log entry, expand/collapse on click.
 *
 * Sprint 61 R-A1: extracted from `routes/audit.tsx` (was inline
 * function). The component owns the visual rendering of one
 * entry; the parent orchestrator owns the expand/collapse map.
 *
 * ## Props
 *
 *   - `entry: AuditEntry` — the row data from `api.getAuditLog`.
 *   - `isOpen: boolean` — whether the JSON detail is shown.
 *   - `onToggle: () => void` — fired on click. The parent
 *     updates the expand/collapse map; this component is
 *     stateless.
 *
 * ## Visual contract
 *
 *   - Compact row: time + event_type + (optional) action +
 *     (optional) target + (optional) exit_code / bytes /
 *     duration_ms. A ▶ glyph at the right edge.
 *   - Expanded: appends the `DataTable` (all `entry.data` keys
 *     + values) and the entry's id + ts.
 *   - Color hint: danger for "blocked" event types; success
 *     for `mac_op_end`; default text color otherwise.
 */
import type { AuditEntry } from "@/types/api";

import { DataTable } from "./DataTable";
import { formatBytes, formatMs, formatTime } from "./format";

export interface AuditNodeProps {
  entry: AuditEntry;
  isOpen: boolean;
  onToggle: () => void;
}

export function AuditNode({ entry, isOpen, onToggle }: AuditNodeProps) {
  const action = String(entry.data?.action ?? "");
  const target = String(entry.data?.target ?? "");
  const isBlocked = entry.event_type.includes("blocked");
  const isEnd = entry.event_type === "mac_op_end";

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
        data-testid="audit-node"
        data-event-type={entry.event_type}
        data-blocked={isBlocked ? "true" : "false"}
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
              <span className="opacity-90 truncate" title={target}>
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
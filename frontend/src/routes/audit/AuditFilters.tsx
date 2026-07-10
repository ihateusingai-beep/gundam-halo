/**
 * AuditFilters — type chips + target search input.
 *
 * Sprint 61 R-A1: extracted from `routes/audit.tsx`. The
 * component owns the filter UI; the orchestrator owns the
 * filter state.
 *
 * ## Props
 *
 *   - `eventTypes: string[]` — the unique event_type values
 *     from the unfiltered log (sorted, deduped). Used to
 *     render the chip row.
 *   - `filterType: string` — currently-active filter
 *     (`"all"` or one of `eventTypes`).
 *   - `setFilterType: (t: string) => void` — chip click handler.
 *   - `targetQuery: string` — current target search substring.
 *   - `setTargetQuery: (q: string) => void` — input change.
 */
import { HudCard } from "@/components/gundam/HudCard";

export interface AuditFiltersProps {
  eventTypes: string[];
  filterType: string;
  setFilterType: (t: string) => void;
  targetQuery: string;
  setTargetQuery: (q: string) => void;
}

export function AuditFilters({
  eventTypes,
  filterType,
  setFilterType,
  targetQuery,
  setTargetQuery,
}: AuditFiltersProps) {
  return (
    <HudCard>
      <div
        className="flex flex-wrap items-center gap-3"
        data-testid="audit-filters"
      >
        <div className="flex items-center gap-1 text-[10px] font-mono">
          <span className="text-[var(--text-muted)] uppercase tracking-wider mr-1 self-center">
            type:
          </span>
          {["all", ...eventTypes].map((t) => (
            <button
              key={t}
              onClick={() => setFilterType(t)}
              data-testid={`audit-filter-chip-${t}`}
              data-active={filterType === t ? "true" : "false"}
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
            data-testid="audit-target-input"
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
  );
}
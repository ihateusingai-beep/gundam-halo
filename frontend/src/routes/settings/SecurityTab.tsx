import { useEffect, useState } from "react";
import { Link } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";
import type { AuditEntry } from "@/types/api";

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

function AuditLine({ entry }: { entry: AuditEntry }) {
  const isBlocked = entry.event_type.includes("blocked");
  const isAlert = entry.event_type === "security_alert";
  const isOk = entry.event_type === "mac_op_audit" || entry.event_type === "mac_op_end";
  const color = isBlocked || isAlert
    ? "var(--danger)"
    : isOk
    ? "var(--text-secondary)"
    : "var(--text-muted)";

  return (
    <div className="flex gap-2 leading-tight py-0.5" style={{ color }}>
      <span className="opacity-60 shrink-0">{entry.ts.slice(11, 19)}</span>
      <span className="shrink-0 uppercase tracking-wider font-bold">
        {entry.event_type}
      </span>
      <span className="opacity-90 truncate flex-1">
        {Object.entries(entry.data)
          .slice(0, 4)
          .map(([k, v]) => `${k}=${truncate(String(v), 30)}`)
          .join(" ")}
      </span>
    </div>
  );
}

export function SecurityTab() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getAuditLog(100)
      .then(setEntries)
      .catch((e) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        setError(msg);
      })
      .finally(() => setLoading(false));
  }, []);

  const eventTypes = Array.from(new Set(entries.map((e) => e.event_type)));
  const filtered =
    filter === "all"
      ? entries
      : entries.filter((e) => e.event_type === filter);

  return (
    <HudCard>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Security — Audit Log
        </h3>
        <div className="flex items-center gap-3">
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {entries.length} entries
          </span>
          <Link
            to="/audit"
            className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] hover:underline"
          >
            ⤴ Open Dashboard
          </Link>
        </div>
      </div>

      {/* Filter chips */}
      {eventTypes.length > 1 && (
        <div className="flex flex-wrap gap-1 mb-3 text-[10px] font-mono">
          <span className="text-[var(--text-muted)] uppercase tracking-wider mr-1 self-center">
            filter:
          </span>
          {["all", ...eventTypes].map((et) => (
            <button
              key={et}
              onClick={() => setFilter(et)}
              className={`px-2 py-0.5 rounded border transition-colors ${
                filter === et
                  ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)]"
              }`}
            >
              {et}
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
          <div className="gundam-radar w-4 h-4" />
          <span>Loading audit log...</span>
        </div>
      ) : error ? (
        <p className="text-[var(--danger)] text-xs">⚠ {error}</p>
      ) : filtered.length === 0 ? (
        <p className="text-[var(--text-muted)] text-xs font-mono">
          {entries.length === 0
            ? "// no audit entries yet — Mac operations will appear here"
            : "// no entries match this filter"}
        </p>
      ) : (
        <div className="font-mono text-[10px] space-y-px max-h-96 overflow-y-auto pr-1">
          {filtered.map((e) => (
            <AuditLine key={e.id} entry={e} />
          ))}
        </div>
      )}
    </HudCard>
  );
}

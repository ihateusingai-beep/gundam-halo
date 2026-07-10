/**
 * DataTable — key-value table for an `entry.data` payload.
 *
 * Sprint 61 R-A1: extracted from `routes/audit.tsx`. Used by
 * `AuditNode` to render the JSON detail when an entry is
 * expanded. Pure component, no state.
 *
 * ## Behaviour
 *
 *   - Empty `data` → renders `(no data)` placeholder.
 *   - Values that are objects → JSON-stringified.
 *   - Other values → `String(v)`.
 *   - Table cells: muted label column + primary value column.
 */
export function DataTable({ data }: { data: Record<string, unknown> }) {
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
/**
 * RadioOption — single-source radio+label+hint widget used by
 * the AsrSection and AlwaysOnSection. Extracted in the Sprint
 * 56.7 mid-implementation audit (P2): 5 instances of the
 * same `<label className="flex items-center gap-2 cursor-pointer
 * select-none"><input type="radio">...<span><span>...</span>`
 * block were duplicated across two sections. Promoted to a
 * shared module so the per-section JSX focuses on which options
 * exist, not the radio chrome.
 *
 * Performance note: the parent renders a `RadioOption` per
 * option. Each is a plain function component (no useState),
 * so the JSX rebuild cost is bounded to the parent's render —
 * no per-option reconciliation overhead.
 */
export function RadioOption({
  name,
  value,
  checked,
  onChange,
  label,
  hint,
}: {
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  label: string;
  hint?: string;
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer select-none">
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={onChange}
        className="accent-[var(--accent)] cursor-pointer"
      />
      <span className="text-xs font-mono text-[var(--text-primary)]">{label}</span>
      {hint && (
        <span className="text-[10px] text-[var(--text-muted)] font-mono">
          {hint}
        </span>
      )}
    </label>
  );
}

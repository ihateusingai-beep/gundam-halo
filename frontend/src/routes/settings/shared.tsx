import type React from "react";

/** Section block — heading bar + children. Used across all settings tabs. */
export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mb-5 last:mb-0">
      <h4 className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest mb-2 border-b border-[var(--border-color)] pb-1">
        {title}
      </h4>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

/** Key/value row with optional mono / accent / danger styling + hint line. */
export function KV({
  label,
  value,
  mono,
  accent,
  danger,
  hint,
}: {
  label: string;
  value: string;
  mono?: boolean;
  accent?: boolean;
  danger?: boolean;
  hint?: string;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 items-baseline">
      <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-[Rajdhani]">
        {label}
      </span>
      <div>
        <span
          className={`text-xs ${mono ? "font-mono" : ""} ${
            accent
              ? "text-[var(--accent)]"
              : danger
              ? "text-[var(--danger)]"
              : "text-[var(--text-primary)]"
          }`}
        >
          {value}
        </span>
        {hint && (
          <div className="text-[9px] text-[var(--text-muted)] font-mono mt-0.5">
            {hint}
          </div>
        )}
      </div>
    </div>
  );
}

/** Vertical list of file paths. */
export function PathList({
  label,
  paths,
  warning,
}: {
  label: string;
  paths: string[];
  warning?: boolean;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 items-start">
      <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-[Rajdhani] pt-0.5">
        {label}
      </span>
      <div className="space-y-0.5">
        {paths.map((p, i) => (
          <div
            key={i}
            className={`text-xs font-mono ${
              warning ? "text-[var(--warning)]" : "text-[var(--text-primary)]"
            }`}
          >
            {p}
          </div>
        ))}
      </div>
    </div>
  );
}

/** ON / OFF indicator with optional hint text. */
export function Toggle({
  label,
  enabled,
  hint,
}: {
  label: string;
  enabled: boolean;
  hint?: string;
}) {
  return (
    <div className="grid grid-cols-[140px_1fr] gap-2 items-center">
      <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-[Rajdhani]">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <span
          className="inline-block w-2 h-2 rounded-full"
          style={{
            background: enabled ? "var(--success)" : "var(--text-muted)",
            boxShadow: enabled ? "0 0 6px var(--success)" : "none",
          }}
        />
        <span
          className="text-xs"
          style={{ color: enabled ? "var(--success)" : "var(--text-muted)" }}
        >
          {enabled ? "ON" : "OFF"}
        </span>
        {hint && (
          <span className="text-[10px] text-[var(--text-muted)] font-mono ml-2">
            — {hint}
          </span>
        )}
      </div>
    </div>
  );
}

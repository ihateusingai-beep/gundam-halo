import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface HoloPanelProps {
  title: string;
  children: ReactNode;
  className?: string;
  collapsed?: boolean;
  onToggle?: () => void;
}

/** `.gundam-holo` — floating holographic panel. */
export function HoloPanel({
  title,
  children,
  className,
  collapsed,
  onToggle,
}: HoloPanelProps) {
  return (
    <div
      className={cn(
        "gundam-holo",
        "bg-[var(--bg-card)] border border-[var(--border-color)] rounded-md backdrop-blur-md",
        "shadow-[0_0_15px_rgba(0,212,255,0.1)]",
        className,
      )}
    >
      <div
        className={cn(
          "flex items-center gap-2 px-3 py-2 border-b border-[var(--border-color)]",
          "text-[var(--accent)] text-xs font-[Orbitron] tracking-widest uppercase",
          onToggle && "cursor-pointer",
        )}
        onClick={onToggle}
      >
        <span>◈</span>
        <span>{title}</span>
        {onToggle && (
          <span className="ml-auto text-[var(--text-muted)]">
            {collapsed ? "+" : "−"}
          </span>
        )}
      </div>
      {!collapsed && <div className="p-3 text-sm font-mono text-[var(--text-secondary)]">{children}</div>}
    </div>
  );
}

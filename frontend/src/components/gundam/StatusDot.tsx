import { cn } from "@/lib/utils";

interface StatusDotProps {
  status: "ok" | "warn" | "alert";
  className?: string;
  label?: string;
}

/** `.gundam-status-ok|warn|alert` — colored dot with pulse. */
export function StatusDot({ status, className, label }: StatusDotProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span
        className={cn(
          status === "ok" && "gundam-status-ok",
          status === "warn" && "gundam-status-warn",
          status === "alert" && "gundam-status-alert",
        )}
        role="status"
        aria-label={`Status: ${status}`}
      >
        ●
      </span>
      {label && (
        <span className="text-xs text-[var(--text-secondary)] font-[Rajdhani] uppercase tracking-wider">
          {label}
        </span>
      )}
    </span>
  );
}

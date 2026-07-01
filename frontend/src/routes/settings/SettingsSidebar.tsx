/**
 * SettingsSidebar — Sprint 50.
 *
 * Vertical sidebar nav replacing the horizontal 8-tab bar. The
 * 8 settings tabs are grouped into 2 sections (Personalisation +
 * System) to make the IA self-explanatory at a glance.
 *
 * Active tab: 3px cyan left border + bg-elevated.
 * Hover: bg-overlay + muted left border.
 *
 * Collapse state persists to localStorage so the rail stays
 * collapsed (or open) across reloads. When collapsed, only the
 * section icons + a vertical rail bar are visible (48px wide).
 *
 * Keyboard nav: j/k (or arrow keys) move down/up; Enter
 * activates the highlighted tab. Mouse is the primary input
 * mode but keyboard works for power users.
 */
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import { SIDEBAR_ENTRIES, type SidebarEntry, type SettingsTab } from "./constants";

interface SettingsSidebarProps {
  active: SettingsTab;
  onChange: (tab: SettingsTab) => void;
}

const COLLAPSE_STORAGE_KEY = "gundam-halo-settings-sidebar-collapsed";

const GROUP_LABELS: Record<SidebarEntry["group"], string> = {
  personalisation: "Personalisation",
  system: "System",
};

function readCollapsed(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(COLLAPSE_STORAGE_KEY) === "true";
}

export function SettingsSidebar({ active, onChange }: SettingsSidebarProps) {
  const [collapsed, setCollapsed] = useState<boolean>(readCollapsed);

  // Persist on change.
  useEffect(() => {
    try {
      localStorage.setItem(COLLAPSE_STORAGE_KEY, collapsed ? "true" : "false");
    } catch {
      // Ignore quota / privacy-mode errors — sidebar still works in-session.
    }
  }, [collapsed]);

  // Keyboard nav: j / ArrowDown move down; k / ArrowUp move up.
  // Enter activates the highlighted entry. Only handles the
  // flat list (groups are visual-only).
  const flatIds = SIDEBAR_ENTRIES.map((e) => e.id);

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const idx = flatIds.indexOf(active);
    if (idx < 0) return;
    if (e.key === "j" || e.key === "ArrowDown") {
      e.preventDefault();
      const next = flatIds[Math.min(flatIds.length - 1, idx + 1)];
      if (next) onChange(next);
    } else if (e.key === "k" || e.key === "ArrowUp") {
      e.preventDefault();
      const prev = flatIds[Math.max(0, idx - 1)];
      if (prev) onChange(prev);
    }
  }

  const groups: SidebarEntry["group"][] = ["personalisation", "system"];

  if (collapsed) {
    // Collapsed rail: just icons + the toggle tab.
    return (
      <aside
        data-testid="settings-sidebar"
        data-collapsed="true"
        className="w-12 shrink-0 border-r border-[var(--border-color)] bg-[var(--bg-elevated)]"
      >
        <button
          type="button"
          data-testid="settings-sidebar-toggle"
          onClick={() => setCollapsed(false)}
          aria-label="Expand settings sidebar"
          title="Expand settings sidebar"
          className="w-full h-10 border-b border-[var(--border-color)] text-[var(--accent)] hover:bg-[var(--bg-overlay)]"
        >
          ▶
        </button>
        <nav className="flex flex-col">
          {SIDEBAR_ENTRIES.map((e) => (
            <button
              key={e.id}
              type="button"
              data-testid={`settings-sidebar-item-${e.id}`}
              data-active={active === e.id ? "true" : "false"}
              onClick={() => onChange(e.id)}
              title={e.label}
              aria-label={e.label}
              aria-current={active === e.id ? "page" : undefined}
              className={cn(
                "h-12 flex items-center justify-center text-lg",
                "border-b border-[var(--border-color)]",
                active === e.id
                  ? "text-[var(--accent)] bg-[var(--bg-overlay)] border-l-[3px] border-l-[var(--accent)]"
                  : "text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--bg-overlay)]",
              )}
            >
              {e.icon}
            </button>
          ))}
        </nav>
      </aside>
    );
  }

  return (
    <aside
      data-testid="settings-sidebar"
      data-collapsed="false"
      className="w-60 shrink-0 border-r border-[var(--border-color)] bg-[var(--bg-elevated)]"
    >
      <div className="flex items-center justify-between h-10 px-3 border-b border-[var(--border-color)]">
        <span className="text-[10px] font-[Rajdhani] uppercase tracking-widest text-[var(--text-muted)]">
          Settings
        </span>
        <button
          type="button"
          data-testid="settings-sidebar-toggle"
          onClick={() => setCollapsed(true)}
          aria-label="Collapse settings sidebar"
          title="Collapse settings sidebar"
          className="text-xs font-mono text-[var(--text-muted)] hover:text-[var(--accent)]"
        >
          ◀
        </button>
      </div>
      <nav
        className="flex flex-col"
        role="tablist"
        aria-label="Settings sections"
        onKeyDown={onKeyDown}
      >
        {groups.map((g) => (
          <div key={g}>
            <div
              data-testid={`settings-sidebar-group-${g}`}
              className="px-3 pt-3 pb-1 text-[9px] font-[Rajdhani] uppercase tracking-widest text-[var(--text-muted)]"
            >
              {GROUP_LABELS[g]}
            </div>
            {SIDEBAR_ENTRIES.filter((e) => e.group === g).map((e) => (
              <button
                key={e.id}
                type="button"
                role="tab"
                data-testid={`settings-sidebar-item-${e.id}`}
                data-active={active === e.id ? "true" : "false"}
                onClick={() => onChange(e.id)}
                aria-selected={active === e.id}
                className={cn(
                  "w-full text-left px-3 py-2 flex items-center gap-2",
                  "border-l-[3px] text-sm font-[Rajdhani] uppercase tracking-wider",
                  "transition-colors",
                  active === e.id
                    ? "text-[var(--accent)] bg-[var(--bg-overlay)] border-l-[var(--accent)]"
                    : "text-[var(--text-muted)] border-l-transparent hover:text-[var(--accent)] hover:bg-[var(--bg-overlay)] hover:border-l-[var(--border-color)]",
                )}
              >
                <span className="opacity-70 w-4 text-center" aria-hidden="true">
                  {e.icon}
                </span>
                <span>{e.label}</span>
              </button>
            ))}
          </div>
        ))}
      </nav>
      <div className="px-3 py-2 mt-auto text-[9px] font-mono text-[var(--text-muted)] border-t border-[var(--border-color)]">
        ↑↓ navigate · click to switch
      </div>
    </aside>
  );
}
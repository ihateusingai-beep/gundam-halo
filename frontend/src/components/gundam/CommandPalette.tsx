/**
 * Global command palette — Cmd+K (Ctrl+K) overlay.
 *
 * Design notes (B6):
 * - One source of truth for actions: a `Command[]` builder hook.
 *   Static actions (nav, theme) are constant; dynamic ones
 *   (jump to project, send to project) are derived from stores.
 * - Fuzzy match is intentionally simple: lowercase substring on
 *   title/subtitle/keywords, scored by match position + title
 *   prefix bonus. Good enough for ~30 commands; we don't pull in
 *   fuse.js for this.
 * - Keyboard: ↑↓ to move, Enter to run, Esc to close. The input
 *   is auto-focused on open and the active item is scrolled into
 *   view (centered).
 * - State is local to the palette. We DO NOT route through zustand
 *   for `open` because open/close is a render-level UI detail and
 *   we want it to vanish with no global side effects.
 *
 * Where to add new actions:
 *   - Add to `useCommands()` for app-level / dynamic actions.
 *   - For one-off, page-local actions, just call `usePalette()`
 *     from a child component and dispatch `openPalette(initialArgs)`.
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { useProjectsStore } from "@/stores/projects";
import { useThemeStore } from "@/stores/theme";
import { api } from "@/lib/api";
import { THEMES } from "@/components/gundam/ThemeSwitcher";

// ---------------------------------------------------------------- //
// Types
// ---------------------------------------------------------------- //

export type CommandCategory =
  | "Navigation"
  | "Projects"
  | "Themes"
  | "Mac Control"
  | "System";

export interface Command {
  id: string;
  title: string;
  subtitle?: string;
  category: CommandCategory;
  keywords?: string[];
  icon?: ReactNode;
  perform: () => void | Promise<void>;
}

interface PaletteOpenEvent {
  category?: CommandCategory;
  initialQuery?: string;
  placeholder?: string;
}

// ---------------------------------------------------------------- //
// Global open/close event bus (no zustand needed)
// ---------------------------------------------------------------- //

const paletteListeners = new Set<(open: boolean, ev?: PaletteOpenEvent) => void>();

export function openPalette(ev: PaletteOpenEvent = {}) {
  paletteListeners.forEach((fn) => fn(true, ev));
}

export function closePalette() {
  paletteListeners.forEach((fn) => fn(false));
}

// ---------------------------------------------------------------- //
// Fuzzy match
// ---------------------------------------------------------------- //

interface ScoredCommand {
  cmd: Command;
  score: number;
}

function scoreCommand(cmd: Command, query: string): number {
  if (!query) return 1; // unfiltered — keep order stable
  const q = query.toLowerCase();
  const title = cmd.title.toLowerCase();
  const subtitle = (cmd.subtitle ?? "").toLowerCase();
  const keywords = (cmd.keywords ?? []).join(" ").toLowerCase();

  // Title prefix is the strongest signal
  if (title.startsWith(q)) return 100 + (10 - title.length);
  if (title.includes(q)) return 50;
  if (subtitle.includes(q)) return 20;
  if (keywords.includes(q)) return 10;
  // Multi-word: each word must appear somewhere
  const words = q.split(/\s+/).filter(Boolean);
  if (words.length > 1 && words.every((w) => title.includes(w) || subtitle.includes(w) || keywords.includes(w))) {
    return 5;
  }
  return 0;
}

// ---------------------------------------------------------------- //
// Hook: command list (static + dynamic)
// ---------------------------------------------------------------- //

function useCommands(): Command[] {
  const navigate = useNavigate();
  const { projects } = useProjectsStore();
  const { theme: currentTheme, setTheme } = useThemeStore();

  return useMemo<Command[]>(() => {
    const cmds: Command[] = [
      // ---- Navigation ----
      {
        id: "nav.overview",
        title: "Go to Overview",
        subtitle: "Mission select / standby view",
        category: "Navigation",
        keywords: ["home", "cockpit", "missions"],
        icon: "▣",
        perform: () => navigate("/"),
      },
      {
        id: "nav.new-project",
        title: "Initialize New Project",
        subtitle: "Create a new mission",
        category: "Navigation",
        keywords: ["new", "create", "add"],
        icon: "+",
        perform: () => navigate("/projects/new"),
      },
      {
        id: "nav.settings",
        title: "Open Settings",
        subtitle: "Secrets, audit log, preferences",
        category: "Navigation",
        keywords: ["config", "preferences"],
        icon: "⚙",
        perform: () => navigate("/settings"),
      },

      // ---- System ----
      {
        id: "sys.refresh-projects",
        title: "Refresh Project List",
        subtitle: "Re-fetch from backend",
        category: "System",
        keywords: ["reload", "fetch"],
        icon: "↻",
        perform: async () => {
          await useProjectsStore.getState().fetchProjects();
          toast.success("Project list refreshed");
        },
      },
      {
        id: "sys.health",
        title: "Run System Health Check",
        subtitle: "Ping backend /health",
        category: "System",
        keywords: ["ping", "status", "diagnostic"],
        icon: "♥",
        perform: async () => {
          try {
            const h = await api.health();
            toast.success("Backend online", {
              description: `${h.status} · v${h.version}`,
            });
          } catch (e) {
            toast.error("Backend unreachable", { description: String(e) });
          }
        },
      },
      {
        id: "sys.gauges",
        title: "Show System Gauges",
        subtitle: "CPU / RAM / Disk snapshot",
        category: "System",
        keywords: ["metrics", "performance", "cpu", "ram", "disk"],
        icon: "≣",
        perform: async () => {
          try {
            const g = await api.getGauges();
            toast("System Gauges", {
              description: `CPU ${g.cpu_percent.toFixed(0)}% · RAM ${g.memory_percent.toFixed(0)}% · DSK ${g.disk_percent.toFixed(0)}%`,
            });
          } catch (e) {
            toast.error("Failed to read gauges", { description: String(e) });
          }
        },
      },

      // ---- Themes ----
      ...THEMES.filter((t): t is typeof t & { id: NonNullable<typeof t.id> } => t.id !== null)
        .map<Command>((t) => ({
          id: `theme.${t.id}`,
          title: `Switch theme: ${t.name}`,
          subtitle: t.description + (currentTheme === t.id ? " (active)" : ""),
          category: "Themes",
          keywords: ["color", "style", "ui", t.id.replace("gundam-", ""), t.emoji],
          icon: t.emoji,
          perform: () => {
            setTheme(t.id);
            toast.success(`Theme: ${t.name}`, { description: t.description });
          },
        })),
      {
        id: "theme.off",
        title: "Disable theme (use defaults)",
        subtitle: "Strip [data-theme] attribute",
        category: "Themes",
        keywords: ["off", "none", "reset", "default"],
        icon: "✖",
        perform: () => {
          setTheme(null as unknown as Parameters<typeof setTheme>[0]);
          toast.success("Theme disabled");
        },
      },

      // ---- Projects (dynamic) ----
      ...projects.map<Command>((p) => ({
        id: `project.jump.${p.name}`,
        title: `Open project: ${p.name}`,
        subtitle: `${p.agent_type} · ${p.status}`,
        category: "Projects" as const,
        keywords: ["go", "view", "mission", p.agent_type, p.status, p.name],
        icon: p.status === "active" ? "◉" : "○",
        perform: () => navigate(`/projects/${p.name}`),
      })),
      ...projects.map<Command>((p) => ({
        id: `project.memory.${p.name}`,
        title: `View memory: ${p.name}`,
        subtitle: "Session history for this project",
        category: "Projects" as const,
        keywords: ["history", "sessions", p.name],
        icon: "◧",
        perform: () => navigate(`/projects/${p.name}/memory`),
      })),

      // ---- Mac Control ----
      {
        id: "mac.read-clipboard",
        title: "Read Clipboard",
        subtitle: "Read macOS clipboard contents",
        category: "Mac Control",
        keywords: ["paste", "copy", "system"],
        icon: "⎘",
        perform: async () => {
          try {
            // Use Tauri clipboard if available, else fall back to a backend read.
            const tauri = (window as any).__TAURI__;
            if (tauri?.clipboard?.readText) {
              const text = await tauri.clipboard.readText();
              toast("Clipboard contents", {
                description: text.length > 200 ? text.slice(0, 200) + "…" : text,
              });
            } else {
              toast.info("Tauri clipboard API not available in web preview");
            }
          } catch (e) {
            toast.error("Clipboard read failed", { description: String(e) });
          }
        },
      },
      {
        id: "mac.system-info",
        title: "Show System Info",
        subtitle: "Platform, Python version, app version",
        category: "Mac Control",
        keywords: ["os", "version", "about"],
        icon: "ⓘ",
        perform: async () => {
          try {
            const info = await api.getSystemInfo();
            toast("System Info", {
              description: `${info.platform} · py ${info.python_version} · app v${info.app_version}`,
            });
          } catch (e) {
            toast.error("Failed to read system info", { description: String(e) });
          }
        },
      },
    ];

    return cmds;
  }, [navigate, projects, currentTheme, setTheme]);
}

// ---------------------------------------------------------------- //
// Recents (localStorage)
// ---------------------------------------------------------------- //

const RECENT_KEY = "gundam-halo.commandPalette.recents";
const RECENT_MAX = 5;

function getRecents(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function pushRecent(id: string) {
  try {
    const cur = getRecents().filter((x) => x !== id);
    cur.unshift(id);
    localStorage.setItem(RECENT_KEY, JSON.stringify(cur.slice(0, RECENT_MAX)));
  } catch {
    /* localStorage unavailable — non-fatal */
  }
}

// ---------------------------------------------------------------- //
// Main component
// ---------------------------------------------------------------- //

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [placeholder, setPlaceholder] = useState("Type a command or search…");
  const [categoryFilter, setCategoryFilter] = useState<CommandCategory | null>(null);
  const [recents, setRecents] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const commands = useCommands();

  // Subscribe to global open/close events
  useEffect(() => {
    const fn = (next: boolean, ev?: PaletteOpenEvent) => {
      setOpen(next);
      if (next) {
        setQuery(ev?.initialQuery ?? "");
        setActive(0);
        setPlaceholder(ev?.placeholder ?? "Type a command or search…");
        setCategoryFilter(ev?.category ?? null);
        setRecents(getRecents());
      }
    };
    paletteListeners.add(fn);
    return () => {
      paletteListeners.delete(fn);
    };
  }, []);

  // Global Cmd/Ctrl+K toggle
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // Auto-focus input on open
  useEffect(() => {
    if (open) {
      // wait for the input to mount
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Filter + score
  const filtered = useMemo<ScoredCommand[]>(() => {
    let pool = commands;
    if (categoryFilter) pool = pool.filter((c) => c.category === categoryFilter);
    return pool
      .map((cmd) => ({ cmd, score: scoreCommand(cmd, query) }))
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score);
  }, [commands, query, categoryFilter]);

  // Reset active when filtered list changes
  useEffect(() => {
    setActive(0);
  }, [query, categoryFilter]);

  // Scroll active item into view
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector<HTMLElement>(
      `[data-idx="${active}"]`,
    );
    el?.scrollIntoView({ block: "nearest" });
  }, [active]);

  const runCommand = useCallback(
    async (cmd: Command) => {
      pushRecent(cmd.id);
      setRecents(getRecents());
      setOpen(false);
      try {
        await cmd.perform();
      } catch (e) {
        toast.error(`Command failed: ${cmd.title}`, { description: String(e) });
      }
    },
    [],
  );

  const onInputKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, Math.max(0, filtered.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(0, a - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const target = filtered[active];
      if (target) void runCommand(target.cmd);
    } else if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "Tab" && !e.shiftKey) {
      // Tab cycles categories: All → Navigation → Projects → Themes → Mac → System → All
      e.preventDefault();
      setCategoryFilter((c) => {
        const order: (CommandCategory | null)[] = [
          null,
          "Navigation",
          "Projects",
          "Themes",
          "Mac Control",
          "System",
        ];
        const idx = c ? order.indexOf(c) : 0;
        return order[(idx + 1) % order.length] ?? null;
      });
    }
  };

  // Group by category for the result list (preserving score order within group)
  const grouped = useMemo(() => {
    const map = new Map<CommandCategory, ScoredCommand[]>();
    for (const s of filtered) {
      const arr = map.get(s.cmd.category) ?? [];
      arr.push(s);
      map.set(s.cmd.category, arr);
    }
    return Array.from(map.entries());
  }, [filtered]);

  if (!open) return null;

  const recentCommands = recents
    .map((id) => commands.find((c) => c.id === id))
    .filter((c): c is Command => Boolean(c));

  return (
    <div
      className="fixed inset-0 z-[10000] flex items-start justify-center pt-[12vh] px-4"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      onMouseDown={(e) => {
        // click on backdrop closes
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        aria-hidden="true"
      />

      {/* Panel */}
      <div
        className={cn(
          "relative w-full max-w-2xl",
          "border border-[var(--accent)] rounded-md",
          "bg-[var(--bg-card)]/95 backdrop-blur-md",
          "shadow-[0_0_40px_-10px_var(--accent)]",
          "overflow-hidden",
        )}
      >
        {/* Scan line overlay (decorative) */}
        <div
          className="pointer-events-none absolute inset-0 opacity-30"
          aria-hidden="true"
          style={{
            background:
              "repeating-linear-gradient(0deg, transparent 0, transparent 3px, rgba(0,212,255,0.04) 3px, rgba(0,212,255,0.04) 4px)",
          }}
        />

        {/* Header / input */}
        <div className="relative flex items-center gap-2 px-4 py-3 border-b border-[var(--border-color)]">
          <span className="text-[var(--accent)] font-[Orbitron] text-lg select-none">
            ⌘
          </span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onInputKey}
            placeholder={placeholder}
            className={cn(
              "flex-1 bg-transparent outline-none",
              "text-[var(--text-primary)] placeholder:text-[var(--text-muted)]",
              "font-mono text-sm",
            )}
            aria-label="Command search"
            autoComplete="off"
            spellCheck={false}
          />
          {categoryFilter && (
            <span className="text-[10px] font-[Rajdhani] uppercase tracking-widest text-[var(--accent)] border border-[var(--accent)] px-2 py-0.5 rounded">
              {categoryFilter} · Tab to cycle
            </span>
          )}
          <kbd className="text-[10px] font-mono text-[var(--text-muted)] border border-[var(--border-color)] rounded px-1.5 py-0.5">
            Esc
          </kbd>
        </div>

        {/* Results */}
        <div
          ref={listRef}
          className="relative max-h-[60vh] overflow-y-auto"
          role="listbox"
        >
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-[var(--text-muted)] text-sm font-mono">
              No commands match "{query}"
            </div>
          )}

          {filtered.length > 0 && recentCommands.length > 0 && query === "" && !categoryFilter && (
            <div className="px-4 pt-3 pb-1">
              <h3 className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
                Recent
              </h3>
            </div>
          )}

          {/* When no query: show recents at top, then categories. Otherwise, score-sorted grouped by category. */}
          {query === "" && !categoryFilter && recentCommands.length > 0 ? (
            <div className="pb-2">
              {recentCommands.map((cmd) => {
                const idxInFiltered = filtered.findIndex((s) => s.cmd.id === cmd.id);
                return (
                  <PaletteRow
                    key={cmd.id}
                    idx={idxInFiltered >= 0 ? idxInFiltered : 0}
                    active={idxInFiltered === active}
                    cmd={cmd}
                    onClick={() => void runCommand(cmd)}
                    onHover={() => {
                      if (idxInFiltered >= 0) setActive(idxInFiltered);
                    }}
                    disabled={idxInFiltered < 0}
                  />
                );
              })}
              <div className="border-t border-[var(--border-color)] my-1" />
            </div>
          ) : null}

          {grouped.map(([category, items]) => (
            <div key={category} className="pb-2">
              <div className="px-4 pt-2 pb-1">
                <h3 className="text-[10px] font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                  {category}
                </h3>
              </div>
              {items.map((s) => {
                const idxInFiltered = filtered.indexOf(s);
                return (
                  <PaletteRow
                    key={s.cmd.id}
                    idx={idxInFiltered}
                    active={idxInFiltered === active}
                    cmd={s.cmd}
                    onClick={() => void runCommand(s.cmd)}
                    onHover={() => setActive(idxInFiltered)}
                  />
                );
              })}
            </div>
          ))}
        </div>

        {/* Footer hint */}
        <div className="relative flex items-center justify-between gap-3 px-4 py-2 border-t border-[var(--border-color)] text-[10px] font-mono text-[var(--text-muted)]">
          <div className="flex items-center gap-3">
            <span>
              <kbd className="border border-[var(--border-color)] rounded px-1 py-0.5 mr-1">↑</kbd>
              <kbd className="border border-[var(--border-color)] rounded px-1 py-0.5 mr-1">↓</kbd>
              navigate
            </span>
            <span>
              <kbd className="border border-[var(--border-color)] rounded px-1 py-0.5 mr-1">↵</kbd>
              run
            </span>
            <span>
              <kbd className="border border-[var(--border-color)] rounded px-1 py-0.5 mr-1">Tab</kbd>
              cycle category
            </span>
          </div>
          <span>{filtered.length} command{filtered.length === 1 ? "" : "s"}</span>
        </div>
      </div>
    </div>
  );
}

interface PaletteRowProps {
  idx: number;
  active: boolean;
  cmd: Command;
  onClick: () => void;
  onHover?: () => void;
  disabled?: boolean;
}

function PaletteRow({ idx, active, cmd, onClick, onHover, disabled }: PaletteRowProps) {
  return (
    <div
      data-idx={idx}
      role="option"
      aria-selected={active}
      onClick={disabled ? undefined : onClick}
      onMouseEnter={() => {
        if (!disabled && onHover) onHover();
      }}
      className={cn(
        "flex items-center gap-3 px-4 py-2 cursor-pointer",
        "transition-colors",
        active && "bg-[var(--accent)]/10 border-l-2 border-[var(--accent)]",
        !active && "border-l-2 border-transparent",
        disabled && "opacity-40",
      )}
    >
      {cmd.icon && (
        <span
          className={cn(
            "w-6 h-6 flex items-center justify-center text-sm shrink-0",
            "border border-[var(--border-color)] rounded",
            active ? "text-[var(--accent)] border-[var(--accent)]" : "text-[var(--text-secondary)]",
          )}
        >
          {cmd.icon}
        </span>
      )}
      <div className="flex-1 min-w-0">
        <div
          className={cn(
            "text-sm font-mono truncate",
            active ? "text-[var(--accent)]" : "text-[var(--text-primary)]",
          )}
        >
          {cmd.title}
        </div>
        {cmd.subtitle && (
          <div className="text-[10px] font-mono text-[var(--text-muted)] truncate">
            {cmd.subtitle}
          </div>
        )}
      </div>
      {active && (
        <span className="text-[10px] font-[Rajdhani] uppercase tracking-widest text-[var(--accent)]">
          ↵
        </span>
      )}
    </div>
  );
}

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
 * - Built on the shadcn `command` primitive (cmdk under the hood):
 *   `<Command>` + `<CommandList>` + `<CommandGroup>` + `<CommandItem>`
 *   + `<CommandEmpty>`. For the input row we drop down to
 *   `CommandPrimitive.Input` (cmdk's bare input) instead of the
 *   shadcn `CommandInput` wrapper, because the wrapper layers in a
 *   styled `InputGroup` and a search icon — we want our own flat
 *   transparent input with a `⌘` prefix and `Esc` hint to match
 *   the existing cockpit visual treatment. We pass
 *   `shouldFilter={false}` on `<Command>` because filtering / scoring
 *   is our job (`scoreCommand`); cmdk's built-in filter would
 *   otherwise fight our ranking. We *do* lean on cmdk for:
 *   arrow-key navigation, selected-item `aria-selected`,
 *   scroll-into-view, and Enter-to-select.
 * - Keyboard: ↑↓ to move (cmdk), Enter to run (cmdk), Esc / Tab are
 *   handled by us on the input (Tab cycles category, Esc closes).
 * - State is local to the palette. We DO NOT route through zustand
 *   for `open` because open/close is a render-level UI detail and
 *   we want it to vanish with no global side effects.
 *
 * Where to add new actions:
 *   - Add to `useCommands()` for app-level / dynamic actions.
 *   - For one-off, page-local actions, just call `usePalette()`
 *     from a child component and dispatch `openPalette(initialArgs)).
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
import { Command as CommandPrimitive } from "cmdk";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

// ---------------------------------------------------------------- //
// Types
// ---------------------------------------------------------------- //

export type CommandCategory =
  | "Navigation"
  | "Projects"
  | "Themes"
  | "Mac Control"
  | "System"
  | "Settings";

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
      {
        id: "nav.audit",
        title: "Open Audit Log",
        subtitle: "Mac control operations — file I/O, shell, policy blocks",
        category: "Navigation",
        keywords: ["security", "audit", "log", "mac"],
        icon: "⛨",
        perform: () => navigate("/audit"),
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

      // ---- Settings (Sprint 51) — deep-link to /settings?tab=<id> so
      //  the SettingsPage URL-sync mounts the right tab content. Without
      //  the query param the user lands on "general" by default.
      {
        id: "settings.general",
        title: "Settings: General",
        subtitle: "User · LLM · Server paths",
        category: "Settings",
        keywords: ["config", "preferences", "user", "llm", "server"],
        icon: "◈",
        perform: () => navigate("/settings?tab=general"),
      },
      {
        id: "settings.voice",
        title: "Settings: Voice",
        subtitle: "Wake phrases · ASR · Corrector · Finetune",
        category: "Settings",
        keywords: ["asr", "tts", "wake", "fine", "tune", "microphone"],
        icon: "◍",
        perform: () => navigate("/settings?tab=voice"),
      },
      {
        id: "settings.themes",
        title: "Settings: Themes",
        subtitle: "Theme + accent color",
        category: "Settings",
        keywords: ["color", "style", "ui", "accent"],
        icon: "◐",
        perform: () => navigate("/settings?tab=themes"),
      },
      {
        id: "settings.memory",
        title: "Settings: User Memory",
        subtitle: "Per-user memory entries",
        category: "Settings",
        keywords: ["memory", "remember", "notes", "annotations"],
        icon: "▣",
        perform: () => navigate("/settings?tab=memory"),
      },
      {
        id: "settings.security",
        title: "Settings: Security",
        subtitle: "Auth · Audit log · Token",
        category: "Settings",
        keywords: ["auth", "token", "audit", "security"],
        icon: "⛨",
        perform: () => navigate("/settings?tab=security"),
      },
      {
        id: "settings.mac",
        title: "Settings: Mac Control",
        subtitle: "File paths · Shell · Accessibility",
        category: "Settings",
        keywords: ["mac", "control", "shell", "file", "system"],
        icon: "⚙",
        perform: () => navigate("/settings?tab=mac"),
      },
      {
        id: "settings.secrets",
        title: "Settings: Secrets",
        subtitle: "API keys & tokens",
        category: "Settings",
        keywords: ["secrets", "api", "keys", "tokens", "credentials"],
        icon: "⚿",
        perform: () => navigate("/settings?tab=secrets"),
      },
      {
        id: "settings.channels",
        title: "Settings: Channels",
        subtitle: "Telegram · Signal · Tailscale",
        category: "Settings",
        keywords: ["telegram", "signal", "tailscale", "channels", "phone"],
        icon: "◉",
        perform: () => navigate("/settings?tab=channels"),
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

const CATEGORY_CYCLE: (CommandCategory | null)[] = [
  null,
  "Navigation",
  "Projects",
  "Themes",
  "Mac Control",
  "System",
  "Settings",
];

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [placeholder, setPlaceholder] = useState("Type a command or search…");
  const [categoryFilter, setCategoryFilter] = useState<CommandCategory | null>(null);
  const [recents, setRecents] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const commands = useCommands();

  // Subscribe to global open/close events
  useEffect(() => {
    const fn = (next: boolean, ev?: PaletteOpenEvent) => {
      setOpen(next);
      if (next) {
        setQuery(ev?.initialQuery ?? "");
        setActiveId(null); // let the filtered list decide
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

  // Auto-focus input on open. cmdk's CommandInput is a forwardRef to
  // the real <input>, so the same ref pattern as before works.
  useEffect(() => {
    if (open) {
      // wait for the input to mount
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  // Filter + score. We always compute this ourselves; cmdk is told
  // `shouldFilter={false}` so it does NOT also filter.
  const filtered = useMemo<ScoredCommand[]>(() => {
    let pool = commands;
    if (categoryFilter) pool = pool.filter((c) => c.category === categoryFilter);
    return pool
      .map((cmd) => ({ cmd, score: scoreCommand(cmd, query) }))
      .filter((s) => s.score > 0)
      .sort((a, b) => b.score - a.score);
  }, [commands, query, categoryFilter]);

  // Keep the highlighted item in sync with the filtered list. When
  // the list changes (new query, new category, new commands), reset
  // the selection to the first item. When cmdk navigates with arrow
  // keys, it calls onValueChange with the new item id, which we
  // echo back to our state so the highlight is correct after a
  // re-render.
  useEffect(() => {
    if (activeId && filtered.some((s) => s.cmd.id === activeId)) return;
    setActiveId(filtered[0]?.cmd.id ?? null);
  }, [filtered, activeId]);

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

  // Key handling that cmdk does NOT do for us:
  //   Esc → close
  //   Tab → cycle category filter
  //   ↑/↓/Enter → handled by cmdk's Command root
  const onInputKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
    } else if (e.key === "Tab" && !e.shiftKey) {
      e.preventDefault();
      setCategoryFilter((c) => {
        const idx = c ? CATEGORY_CYCLE.indexOf(c) : 0;
        return CATEGORY_CYCLE[(idx + 1) % CATEGORY_CYCLE.length] ?? null;
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

        {/* Header / input row. The prefix glyph, the ⌘ chip, and
            the category-filter chip are decorative siblings of the
            CommandInput, which is a cmdk <input>. */}
        <div className="relative flex items-center gap-2 px-4 py-3 border-b border-[var(--border-color)]">
          <span className="text-[var(--accent)] font-[Orbitron] text-lg select-none">
            ⌘
          </span>
          <CommandPrimitive.Input
            ref={inputRef}
            value={query}
            onValueChange={setQuery}
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
        <Command
          shouldFilter={false}
          value={activeId ?? ""}
          onValueChange={setActiveId}
          className={cn(
            "relative max-h-[60vh] overflow-y-auto bg-transparent",
            "[&_[cmdk-list-sizer]]:!p-0",
          )}
          label="Command results"
        >
          <CommandList
            className="max-h-none"
          >
            {filtered.length === 0 && (
              <CommandEmpty
                className={cn(
                  "px-4 py-8 text-center text-[var(--text-muted)] text-sm font-mono",
                )}
              >
                No commands match "{query}"
              </CommandEmpty>
            )}

            {filtered.length > 0 &&
              recentCommands.length > 0 &&
              query === "" &&
              !categoryFilter && (
                <div className="px-4 pt-3 pb-1">
                  <h3 className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
                    Recent
                  </h3>
                </div>
              )}

            {/* When no query: show recents at top, then categories. Otherwise, score-sorted grouped by category. */}
            {query === "" && !categoryFilter && recentCommands.length > 0
              ? (
                <CommandGroup
                  heading=""
                  className="!p-0 !pb-2"
                >
                  {recentCommands.map((cmd) => {
                    const idxInFiltered = filtered.findIndex((s) => s.cmd.id === cmd.id);
                    const disabled = idxInFiltered < 0;
                    return (
                      <CommandItem
                        key={cmd.id}
                        value={cmd.id}
                        disabled={disabled}
                        onSelect={() => {
                          if (!disabled) void runCommand(cmd);
                        }}
                        className={cn(
                          // Override cmdk's default selection styling with our
                          // Gundam tokens. cmdk adds `data-selected="true"`
                          // on the highlighted item.
                          "flex items-center gap-3 px-4 py-2 cursor-pointer",
                          "transition-colors rounded-none border-l-2 border-transparent",
                          "data-[selected=true]:bg-[var(--accent)]/10",
                          "data-[selected=true]:border-[var(--accent)]",
                          "data-[disabled=true]:opacity-40",
                          "[&[data-selected=true]_.gundam-row-title]:text-[var(--accent)]",
                          "[&[data-selected=true]_.gundam-row-icon]:text-[var(--accent)]",
                          "[&[data-selected=true]_.gundam-row-icon]:border-[var(--accent)]",
                        )}
                      >
                        <PaletteRowContent cmd={cmd} />
                      </CommandItem>
                    );
                  })}
                  <div className="border-t border-[var(--border-color)] my-1" />
                </CommandGroup>
              )
              : null}

            {grouped.map(([category, items]) => (
              <CommandGroup
                key={category}
                heading={category}
                className="!p-0 !pb-2 [&_[cmdk-group-heading]]:px-4 [&_[cmdk-group-heading]]:pt-2 [&_[cmdk-group-heading]]:pb-1 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-[Orbitron] [&_[cmdk-group-heading]]:text-[var(--accent)] [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-widest"
              >
                {items.map((s) => (
                  <CommandItem
                    key={s.cmd.id}
                    value={s.cmd.id}
                    onSelect={() => void runCommand(s.cmd)}
                    className={cn(
                      "flex items-center gap-3 px-4 py-2 cursor-pointer",
                      "transition-colors rounded-none border-l-2 border-transparent",
                      "data-[selected=true]:bg-[var(--accent)]/10",
                      "data-[selected=true]:border-[var(--accent)]",
                      "[&[data-selected=true]_.gundam-row-title]:text-[var(--accent)]",
                      "[&[data-selected=true]_.gundam-row-icon]:text-[var(--accent)]",
                      "[&[data-selected=true]_.gundam-row-icon]:border-[var(--accent)]",
                    )}
                  >
                    <PaletteRowContent cmd={s.cmd} />
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>

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

// ---------------------------------------------------------------- //
// Row content (extracted so both recent and grouped items render
// identically). The outer <CommandItem> owns selection styling;
// this is purely the icon / title / subtitle / enter-glyph.
// ---------------------------------------------------------------- //

function PaletteRowContent({ cmd }: { cmd: Command }) {
  return (
    <>
      {cmd.icon && (
        <span
          className={cn(
            "gundam-row-icon",
            "w-6 h-6 flex items-center justify-center text-sm shrink-0",
            "border border-[var(--border-color)] rounded",
            "text-[var(--text-secondary)]",
          )}
        >
          {cmd.icon}
        </span>
      )}
      <div className="flex-1 min-w-0">
        <div
          className={cn(
            "gundam-row-title",
            "text-sm font-mono truncate text-[var(--text-primary)]",
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
      <span
        className={cn(
          "gundam-row-enter",
          "text-[10px] font-[Rajdhani] uppercase tracking-widest text-[var(--accent)]",
          // Only show the ↵ glyph on the currently highlighted row.
          "opacity-0 group-data-[selected=true]/command-item:opacity-100",
        )}
        aria-hidden="true"
      >
        ↵
      </span>
    </>
  );
}

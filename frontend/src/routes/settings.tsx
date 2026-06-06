import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { StatusDot } from "@/components/gundam/StatusDot";
import { api, ApiError } from "@/lib/api";
import { useThemeStore, type CockpitBackground } from "@/stores/theme";
import { THEMES } from "@/components/gundam/ThemeSwitcher";
import type { AuditEntry, Settings } from "@/types/api";

type Tab = "general" | "mac" | "channels" | "themes" | "security";

const TABS: Array<{ id: Tab; label: string; icon: string }> = [
  { id: "general", label: "General", icon: "◈" },
  { id: "mac", label: "Mac Control", icon: "⚙" },
  { id: "channels", label: "Channels", icon: "◉" },
  { id: "themes", label: "Themes", icon: "◐" },
  { id: "security", label: "Security", icon: "⛨" },
];

interface BgOption {
  id: CockpitBackground;
  label: string;
  description: string;
  thumb: string | null;
}

const BACKGROUNDS: BgOption[] = [
  { id: "none",    label: "NONE",    description: "Pure hex grid — fast, no asset", thumb: null },
  { id: "core-01", label: "CORE-01", description: "Psychoframe — pink pulse",       thumb: "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg" },
  { id: "core-02", label: "CORE-02", description: "Psychoframe — cyan glow",        thumb: "/gundam-assets/backgrounds/bg-unicorn-core-02.jpg" },
  { id: "core-03", label: "CORE-03", description: "Psychoframe — strong pulse",     thumb: "/gundam-assets/backgrounds/bg-unicorn-core-03.jpg" },
  { id: "core-04", label: "CORE-04", description: "Psychoframe — soft glow",        thumb: "/gundam-assets/backgrounds/bg-unicorn-core-04.jpg" },
];

/** Settings page — 5 tabs: General / Mac Control / Channels / Themes / Security. */
export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<Tab>("general");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    api
      .getSettings()
      .then(setSettings)
      .catch((e) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        setError(msg);
        toast.error("Failed to load settings", { description: msg });
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading settings...</p>
        </div>
      </HudCard>
    );
  }

  if (error || !settings) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error || "No settings available"}</p>
      </HudCard>
    );
  }

  return (
    <div className="space-y-3">
      {/* Tab nav */}
      <HudCard className="!p-0">
        <div className="flex overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex-1 min-w-[120px] px-4 py-3 text-sm font-[Rajdhani] uppercase tracking-wider transition-colors border-b-2 ${
                activeTab === t.id
                  ? "text-[var(--accent)] border-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "text-[var(--text-muted)] border-transparent hover:text-[var(--accent)] hover:border-[var(--border-color)]"
              }`}
            >
              <span className="mr-2 opacity-70">{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>
      </HudCard>

      {/* Tab content */}
      {activeTab === "general" && <GeneralTab settings={settings} />}
      {activeTab === "mac" && <MacTab settings={settings} />}
      {activeTab === "channels" && <ChannelsTab settings={settings} />}
      {activeTab === "themes" && <ThemesTab />}
      {activeTab === "security" && <SecurityTab />}
    </div>
  );
}

// ──────────────────────────────────────────────────────────────────────
// General
// ──────────────────────────────────────────────────────────────────────

function GeneralTab({ settings }: { settings: Settings }) {
  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        General
      </h3>

      <Section title="LLM (Brain)">
        <KV label="Provider" value={settings.llm.provider} />
        <KV label="Base URL" value={settings.llm.base_url} mono />
        <KV label="Default Model" value={settings.llm.default_model} accent />
        <KV label="Fallback Model" value={settings.llm.fallback_model} />
        <KV
          label="API Key"
          value={settings.llm.api_key_configured ? "✓ configured" : "✗ not configured"}
          accent={settings.llm.api_key_configured}
          danger={!settings.llm.api_key_configured}
        />
      </Section>

      <Section title="Server">
        <KV label="Host" value={settings.server.host} mono />
        <KV label="Port" value={String(settings.server.port)} mono />
        <KV label="Log Level" value={settings.server.log_level} />
        <KV
          label="Tailscale Required"
          value={settings.server.require_tailscale ? "yes" : "no"}
        />
        <KV label="Tailscale Hostname" value={settings.server.tailscale_hostname} mono />
      </Section>

      <Section title="User">
        <KV label="Name" value={settings.user.name} />
        <KV label="Default Theme" value={settings.user.default_theme} />
      </Section>

      <Section title="Paths">
        <KV label="HALO_HOME" value={settings.app.home} mono />
        <KV
          label="Config File"
          value={settings.app.config_path}
          mono
          hint="Edit TOML to change settings; restart server to apply"
        />
        <KV label="Version" value={settings.app.version} mono />
      </Section>
    </HudCard>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Mac Control
// ──────────────────────────────────────────────────────────────────────

function MacTab({ settings }: { settings: Settings }) {
  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        Mac Control
      </h3>

      <Section title="Path Policy">
        <KV
          label="Default Mode"
          value={settings.mac.default_path_policy}
          accent
          hint="project_only | user_home | allowlist"
        />
        <PathList
          label="File Read Paths"
          paths={settings.mac.file_read_paths}
        />
        <PathList
          label="File Write Paths"
          paths={settings.mac.file_write_paths}
          warning
        />
      </Section>

      <Section title="Shell Allowlist">
        <p className="text-[10px] text-[var(--text-muted)] font-mono mb-2">
          Commands the agent can run. Edit in config.toml.
        </p>
        <div className="flex flex-wrap gap-1">
          {settings.mac.shell_allowlist.map((c) => (
            <span
              key={c}
              className="px-2 py-0.5 text-[10px] font-mono border border-[var(--border-color)] text-[var(--accent)] rounded bg-[var(--bg-input)]"
            >
              {c}
            </span>
          ))}
        </div>
      </Section>

      <Section title="Capabilities">
        <Toggle
          label="AppleScript"
          enabled={settings.mac.apple_script_enabled}
          hint="macOS automation via osascript"
        />
        <Toggle
          label="Notifications"
          enabled={settings.mac.notifications_enabled}
          hint="System notifications via osascript"
        />
        <Toggle
          label="Accessibility API"
          enabled={settings.mac.a11y_enabled}
          hint="Deep UI control — requires permission"
        />
      </Section>
    </HudCard>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Channels
// ──────────────────────────────────────────────────────────────────────

function ChannelsTab({ settings }: { settings: Settings }) {
  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        Channels
      </h3>

      <Section title="Telegram">
        <div className="flex items-center gap-2 mb-2">
          <StatusDot
            status={settings.telegram.enabled ? "ok" : "warn"}
            label={settings.telegram.enabled ? "ENABLED" : "DISABLED"}
          />
        </div>
        <KV
          label="Bot Token"
          value={settings.telegram.bot_token_configured ? "✓ configured" : "✗ not configured"}
          accent={settings.telegram.bot_token_configured}
          danger={!settings.telegram.bot_token_configured}
        />
        <KV label="Command Prefix" value={settings.telegram.command_prefix} mono />
        <KV
          label="Allowed Chat IDs"
          value={
            settings.telegram.allowed_chat_ids.length === 0
              ? "(none — no one can message)"
              : settings.telegram.allowed_chat_ids.join(", ")
          }
          mono
        />
        <p className="text-[10px] text-[var(--text-muted)] font-mono mt-2">
          Configure in <code>~/.gundam-halo/config.toml</code> under <code>[telegram]</code>.
        </p>
      </Section>

      <Section title="Future Channels">
        <p className="text-xs text-[var(--text-muted)] font-mono">
          Signal / iMessage / Discord — coming after v1.
        </p>
      </Section>
    </HudCard>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Themes
// ──────────────────────────────────────────────────────────────────────

function ThemesTab() {
  const { theme, setTheme, background, setBackground } = useThemeStore();
  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        Themes
      </h3>
      <Section title="Theme">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {THEMES.map((t) => (
            <button
              key={t.id}
              onClick={() => {
                setTheme(t.id);
                toast.success(`Theme → ${t.name}`, { description: t.description });
              }}
              className={`p-3 rounded border text-left transition-all hover:border-[var(--accent)] ${
                theme === t.id
                  ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "border-[var(--border-color)] bg-[var(--bg-card)]"
              }`}
            >
              <div className="text-2xl">{t.emoji}</div>
              <div className="text-sm font-[Rajdhani] uppercase tracking-wider mt-1">
                {t.name}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">
                {t.description}
              </div>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Cockpit Background">
        <p className="text-xs text-[var(--text-muted)] mb-3 font-mono">
          Default: pure CSS hex grid. Optional: 4 NT-D psychoframe JPGs.
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
          {BACKGROUNDS.map((b) => (
            <button
              key={b.id}
              onClick={() => {
                setBackground(b.id);
                toast.success(`Background → ${b.label}`, { description: b.description });
              }}
              className={`p-2 rounded border text-left transition-all hover:border-[var(--accent)] ${
                background === b.id
                  ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "border-[var(--border-color)] bg-[var(--bg-card)]"
              }`}
            >
              <div
                className="w-full h-16 rounded mb-2 border border-[var(--border-color)] overflow-hidden flex items-center justify-center"
                style={
                  b.thumb
                    ? {
                        backgroundImage: `url(${b.thumb})`,
                        backgroundSize: "cover",
                        backgroundPosition: "center",
                        filter: "brightness(0.7) saturate(1.1)",
                      }
                    : {
                        backgroundImage:
                          "repeating-linear-gradient(60deg, transparent 0 8px, rgba(0,212,255,0.08) 8px 9px), repeating-linear-gradient(120deg, transparent 0 8px, rgba(0,212,255,0.08) 8px 9px)",
                      }
                }
              />
              <div className="text-sm font-[Rajdhani] uppercase tracking-wider">
                {b.label}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">
                {b.description}
              </div>
            </button>
          ))}
        </div>
      </Section>
    </HudCard>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Security
// ──────────────────────────────────────────────────────────────────────

function SecurityTab() {
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
  const filtered = filter === "all"
    ? entries
    : entries.filter((e) => e.event_type === filter);

  return (
    <HudCard>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Security — Audit Log
        </h3>
        <span className="text-[10px] text-[var(--text-muted)] font-mono">
          {entries.length} entries
        </span>
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

function truncate(s: string, n: number): string {
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

// ──────────────────────────────────────────────────────────────────────
// Shared bits
// ──────────────────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-5 last:mb-0">
      <h4 className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest mb-2 border-b border-[var(--border-color)] pb-1">
        {title}
      </h4>
      <div className="space-y-1.5">{children}</div>
    </div>
  );
}

function KV({
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
            accent ? "text-[var(--accent)]" : danger ? "text-[var(--danger)]" : "text-[var(--text-primary)]"
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

function PathList({ label, paths, warning }: { label: string; paths: string[]; warning?: boolean }) {
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

function Toggle({
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

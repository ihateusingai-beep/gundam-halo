import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { StatusDot } from "@/components/gundam/StatusDot";
import { api, ApiError } from "@/lib/api";
import {
  getAnimationSpeed,
  setAnimationSpeed,
} from "@/services/halo-tray-controls";
import { useThemeStore, type CockpitBackground } from "@/stores/theme";
import { THEMES } from "@/components/gundam/ThemeSwitcher";
import type { AuditEntry, MemoryEntry, Settings } from "@/types/api";

type Tab = "general" | "mac" | "channels" | "themes" | "security" | "secrets" | "memory";

const TABS: Array<{ id: Tab; label: string; icon: string }> = [
  { id: "general", label: "General", icon: "◈" },
  { id: "mac", label: "Mac Control", icon: "⚙" },
  { id: "channels", label: "Channels", icon: "◉" },
  { id: "themes", label: "Themes", icon: "◐" },
  { id: "security", label: "Security", icon: "⛨" },
  { id: "secrets", label: "Secrets", icon: "⚿" },
  { id: "memory", label: "User Memory", icon: "▣" },
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
      {activeTab === "secrets" && <SecretsTab />}
      {activeTab === "memory" && <MemoryTab />}
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

      <Section title="Tray Icon Animation">
        <TraySpeedControl />
      </Section>
    </HudCard>
  );
}

// ──────────────────────────────────────────────────────────────────────
// Tray animation speed (M3-B8)
// ──────────────────────────────────────────────────────────────────────

const SPEED_PRESETS: Array<{
  fps: number;
  label: string;
  description: string;
}> = [
  { fps: 8, label: "Battery Saver", description: "8 FPS — minimal visual noise" },
  { fps: 15, label: "Default", description: "15 FPS — smooth, low CPU" },
  { fps: 24, label: "Cinema", description: "24 FPS — animation feels alive" },
];

function TraySpeedControl() {
  const [fps, setFps] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // Read current FPS on mount
  useEffect(() => {
    getAnimationSpeed().then(setFps).catch(() => setFps(15));
  }, []);

  const applyFps = async (next: number, presetLabel?: string) => {
    if (saving) return;
    setSaving(true);
    try {
      const effective = await setAnimationSpeed(next);
      setFps(effective);
      if (presetLabel) {
        toast.success(`Tray → ${presetLabel}`, {
          description: `${effective} FPS · effective value`,
        });
      }
    } catch (e) {
      toast.error("Failed to set tray speed", { description: String(e) });
    } finally {
      setSaving(false);
    }
  };

  // Map 1..60 to 0..100 for the slider fill gradient
  const fillPct = fps == null ? 25 : ((fps - 1) / 59) * 100;

  return (
    <div className="space-y-3">
      {/* Current value + slider */}
      <div className="grid grid-cols-[140px_1fr_60px] gap-3 items-center">
        <span className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-[Rajdhani]">
          Speed
        </span>
        <input
          type="range"
          min={1}
          max={60}
          step={1}
          value={fps ?? 15}
          disabled={fps == null || saving}
          onChange={(e) => applyFps(parseInt(e.target.value, 10))}
          className="gundam-slider"
          style={{ ["--gundam-slider-fill" as any]: `${fillPct}%` }}
          aria-label="Tray animation FPS"
        />
        <div className="text-right">
          <span
            className="text-lg font-[Orbitron] tabular-nums"
            style={{ color: "var(--accent)" }}
          >
            {fps ?? "—"}
          </span>
          <span className="text-[10px] text-[var(--text-muted)] ml-1 font-mono">
            fps
          </span>
        </div>
      </div>

      {/* Preset chips */}
      <div className="grid grid-cols-3 gap-2">
        {SPEED_PRESETS.map((p) => {
          const isActive = fps === p.fps;
          return (
            <button
              key={p.fps}
              onClick={() => applyFps(p.fps, p.label)}
              disabled={saving}
              className={`p-2 rounded border text-left transition-all hover:border-[var(--accent)] ${
                isActive
                  ? "border-[var(--accent)] bg-[var(--bg-elevated)]"
                  : "border-[var(--border-color)] bg-[var(--bg-card)]"
              }`}
            >
              <div className="text-xs font-[Rajdhani] uppercase tracking-wider text-[var(--text-primary)]">
                {p.label}
              </div>
              <div className="text-[10px] text-[var(--text-muted)] font-mono">
                {p.description}
              </div>
            </button>
          );
        })}
      </div>

      <p className="text-[10px] text-[var(--text-muted)] font-mono">
        Runtime-tunable · resets to 15 FPS on app restart · persistence in v1.1
      </p>
    </div>
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

// ──────────────────────────────────────────────────────────────────────
// Secrets (M6+) — runtime secret management
// ──────────────────────────────────────────────────────────────────────

type SecretStatus = {
  label: string;
  configured: boolean;
  source: "override" | "env" | "none";
};

type SecretMap = Record<string, SecretStatus>;

const SECRET_INPUT_CLASS =
  "w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded px-2 py-1 text-xs font-mono " +
  "text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] " +
  "placeholder:text-[var(--text-muted)]/50";

/** Secrets tab — manage MiniMax API key + Telegram bot token from the UI.
 *
 * Security properties:
 * - Server NEVER returns the secret value in any response
 * - We only render the configured/source status from GET
 * - Password inputs use autocomplete="new-password" + autoComplete="off"
 *   to discourage browser autofill / saved-password manager capture
 * - Local component state is wiped on unmount (no React DevTools
 *   persistence of the value beyond the lifetime of the form)
 * - onSave success → reset the input field to "" (so the value
 *   isn't lingering in the DOM)
 */
function SecretsTab() {
  const [status, setStatus] = useState<SecretMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Two parallel string states. We deliberately never combine into
  // a single object so React can't share memoisation between them.
  const [minimax, setMinimax] = useState("");
  const [telegram, setTelegram] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = async () => {
    try {
      setError(null);
      const data = await api.getSecrets();
      setStatus(data);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleSave = async () => {
    const items: Array<{ name: string; value: string }> = [];
    if (minimax.trim()) items.push({ name: "MINIMAX_API_KEY", value: minimax });
    if (telegram.trim()) items.push({ name: "GUNDAM_HALO_TG_TOKEN", value: telegram });
    if (items.length === 0) {
      toast.error("Nothing to save", { description: "Type a value first." });
      return;
    }
    setSaving(true);
    try {
      const updated = await api.setSecrets(items);
      setStatus(updated);
      setMinimax("");
      setTelegram("");
      toast.success("Secrets saved", {
        description:
          "Takes effect on the next LLM / Telegram request. No restart required.",
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to save secrets", { description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async (name: "MINIMAX_API_KEY" | "GUNDAM_HALO_TG_TOKEN") => {
    setSaving(true);
    try {
      const updated = await api.deleteSecret(name);
      setStatus(updated);
      toast.success("Secret cleared");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to clear", { description: msg });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading secrets…</p>
        </div>
      </HudCard>
    );
  }

  if (error) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  const minimaxStatus = status?.["MINIMAX_API_KEY"];
  const telegramStatus = status?.["GUNDAM_HALO_TG_TOKEN"];

  return (
    <HudCard>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Secrets
        </h3>
        <span className="text-[10px] text-[var(--text-muted)] font-mono">
          M6 · runtime-managed
        </span>
      </div>

      <p className="text-xs text-[var(--text-muted)] font-mono mb-4">
        Values are sent over your local / Tailscale network to the backend, persisted
        to <code>~/.gundam-halo/.env</code> with <code>0600</code> permissions, and
        mirrored into the running process. They take effect on the next LLM / Telegram
        request — no server restart required. The server never returns values, only
        whether each one is configured.
      </p>

      <div className="space-y-4">
        <SecretInput
          name="MINIMAX_API_KEY"
          label={minimaxStatus?.label ?? "MiniMax API Key"}
          value={minimax}
          configured={!!minimaxStatus?.configured}
          source={minimaxStatus?.source ?? "none"}
          onChange={setMinimax}
          onClear={() => handleClear("MINIMAX_API_KEY")}
          disabled={saving}
        />

        <SecretInput
          name="GUNDAM_HALO_TG_TOKEN"
          label={telegramStatus?.label ?? "Telegram Bot Token"}
          value={telegram}
          configured={!!telegramStatus?.configured}
          source={telegramStatus?.source ?? "none"}
          onChange={setTelegram}
          onClear={() => handleClear("GUNDAM_HALO_TG_TOKEN")}
          disabled={saving}
        />
      </div>

      <div className="flex items-center justify-end gap-2 mt-4 pt-4 border-t border-[var(--border-color)]">
        <button
          onClick={refresh}
          disabled={saving}
          className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40"
        >
          Refresh
        </button>
        <button
          onClick={handleSave}
          disabled={saving || (!minimax.trim() && !telegram.trim())}
          className="px-4 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </HudCard>
  );
}

function SecretInput({
  name,
  label,
  value,
  configured,
  source,
  onChange,
  onClear,
  disabled,
}: {
  name: string;
  label: string;
  value: string;
  configured: boolean;
  source: "override" | "env" | "none";
  onChange: (v: string) => void;
  onClear: () => void;
  disabled: boolean;
}) {
  const sourceLabel =
    source === "override"
      ? "stored in .env"
      : source === "env"
      ? "from environment"
      : "not set";
  const sourceColor =
    source === "override"
      ? "var(--accent)"
      : source === "env"
      ? "var(--warning)"
      : "var(--text-muted)";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-[Rajdhani]">
          {label}{" "}
          <span className="text-[var(--text-muted)]/50 font-mono normal-case">
            ({name})
          </span>
        </label>
        <span
          className="text-[10px] font-mono flex items-center gap-1.5"
          style={{ color: sourceColor }}
          title={
            source === "none"
              ? "Type a value below and click Save"
              : `Active source: ${sourceLabel}`
          }
        >
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{
              background: configured ? sourceColor : "var(--text-muted)",
              boxShadow: configured ? `0 0 6px ${sourceColor}` : "none",
            }}
          />
          {configured ? sourceLabel : "not set"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="password"
          autoComplete="off"
          spellCheck={false}
          data-1p-ignore
          // Hint to password managers (1Password / Bitwarden) not to store
          data-bwignore
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            configured
              ? "••••••••  (type to replace, leave blank to keep)"
              : `Paste your ${name}…`
          }
          className={SECRET_INPUT_CLASS}
          aria-label={label}
        />
        {configured && (
          <button
            onClick={onClear}
            disabled={disabled}
            className="px-2 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
            title={`Clear ${name}`}
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Memory (M7-Phase-2.5) — read-only viewer for the agent's per-user memory
// ---------------------------------------------------------------------------

function formatTimestamp(epoch: number): string {
  if (!epoch) return "—";
  try {
    const d = new Date(epoch * 1000);
    return d.toLocaleString();
  } catch {
    return String(epoch);
  }
}

/** Memory tab — list all users, expand to see their memory entries, delete the wrong ones. */
function MemoryTab() {
  const [users, setUsers] = useState<string[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [entries, setEntries] = useState<MemoryEntry[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(true);
  const [loadingEntries, setLoadingEntries] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deletingKey, setDeletingKey] = useState<string | null>(null);

  const refreshUsers = async () => {
    try {
      setError(null);
      setLoadingUsers(true);
      const data = await api.listMemoryUsers();
      setUsers(data.users);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
    } finally {
      setLoadingUsers(false);
    }
  };

  const refreshEntries = async (user: string) => {
    try {
      setError(null);
      setLoadingEntries(true);
      const data = await api.listMemoryEntries(user);
      setEntries(data.entries);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
      setEntries([]);
    } finally {
      setLoadingEntries(false);
    }
  };

  useEffect(() => {
    refreshUsers();
  }, []);

  useEffect(() => {
    if (selected) {
      refreshEntries(selected);
    } else {
      setEntries([]);
    }
  }, [selected]);

  const handleDelete = async (user: string, key: string) => {
    const ok = window.confirm(
      `Delete memory[${key}] for user "${user}"? This cannot be undone.`,
    );
    if (!ok) return;
    setDeletingKey(key);
    try {
      await api.deleteMemoryEntry(user, key);
      toast.success("Memory entry deleted", {
        description: `${user} / ${key}`,
      });
      await refreshEntries(user);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to delete", { description: msg });
    } finally {
      setDeletingKey(null);
    }
  };

  if (loadingUsers) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading users…</p>
        </div>
      </HudCard>
    );
  }

  if (error && users.length === 0) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  return (
    <div className="space-y-4">
      <HudCard>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
            User Memory
          </h3>
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            M7-Phase-2.5 · read-only viewer
          </span>
        </div>

        <p className="text-xs text-[var(--text-muted)] font-mono mb-4">
          The agent's per-user key/value memory (M7-Phase-2). When the agent
          learns a fact about you (preferred name, timezone, favorite Gundam,
          …) it appears here. Auto-injected into the system prompt on every
          turn. You can{" "}
          <span className="text-[var(--danger)]">delete</span> an entry the
          agent got wrong — the next turn will not see it. The dashboard
          never writes new entries; the agent does that via{" "}
          <code>memory_write</code>.
        </p>

        {users.length === 0 ? (
          <div className="p-4 border border-dashed border-[var(--border-color)] text-center">
            <p className="text-xs text-[var(--text-muted)] font-mono">
              No users yet. Start a conversation — when the agent calls{" "}
              <code>memory_write</code>, you'll see the user here.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2">
            {users.map((u) => (
              <button
                key={u}
                onClick={() => setSelected(u)}
                className={`px-3 py-2 text-xs font-[Rajdhani] uppercase tracking-wider border transition-colors ${
                  selected === u
                    ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)]"
                    : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                }`}
              >
                {u}
              </button>
            ))}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 mt-4 pt-4 border-t border-[var(--border-color)]">
          <button
            onClick={refreshUsers}
            className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
          >
            Refresh
          </button>
        </div>
      </HudCard>

      {selected && (
        <HudCard>
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
              {selected}
            </h4>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              {loadingEntries
                ? "loading…"
                : `${entries.length} ${entries.length === 1 ? "entry" : "entries"}`}
            </span>
          </div>

          {loadingEntries ? (
            <div className="flex items-center gap-3">
              <div className="gundam-radar w-6 h-6" />
              <p className="text-xs text-[var(--text-muted)] font-mono">
                Loading entries…
              </p>
            </div>
          ) : entries.length === 0 ? (
            <p className="text-xs text-[var(--text-muted)] font-mono">
              No entries yet for this user.
            </p>
          ) : (
            <div className="space-y-2">
              {entries.map((e) => (
                <div
                  key={e.key}
                  className="border border-[var(--border-color)] bg-[var(--bg-elevated)] p-3"
                >
                  <div className="flex items-center justify-between mb-1 gap-2">
                    <code className="text-[11px] text-[var(--accent)] font-mono break-all">
                      {e.key}
                    </code>
                    <button
                      onClick={() => handleDelete(selected, e.key)}
                      disabled={deletingKey === e.key}
                      className="px-2 py-0.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 shrink-0"
                    >
                      {deletingKey === e.key ? "…" : "Delete"}
                    </button>
                  </div>
                  <p className="text-xs text-[var(--text)] font-mono whitespace-pre-wrap break-words">
                    {e.value}
                  </p>
                  <p className="text-[10px] text-[var(--text-muted)] font-mono mt-2">
                    updated {formatTimestamp(e.updated_at)} · created{" "}
                    {formatTimestamp(e.created_at)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </HudCard>
      )}
    </div>
  );
}

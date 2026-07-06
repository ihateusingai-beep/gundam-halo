import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import {
  getAnimationSpeed,
  setAnimationSpeed,
} from "@/services/halo-tray-controls";
import type { Settings } from "@/types/api";
import { api } from "@/lib/api";

import { SPEED_PRESETS } from "../constants";
import { KV, Section } from "../shared";

const SPEED_FILL_PCT = (fps: number | null): string => {
  if (fps == null) return "25%";
  return `${((fps - 1) / 59) * 100}%`;
};

/** True only inside the Tauri desktop runtime. Tray controls rely on
 *  Rust commands (`set_animation_speed` / `get_animation_speed`) that
 *  are unavailable in a plain browser, so we hide the entire section
 *  on the web dev server to avoid throwing on every slider change. */
function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof (window as any).__TAURI_INTERNALS__ !== "undefined"
  );
}

function TraySpeedControl() {
  const [fps, setFps] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

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
          style={{ ["--gundam-slider-fill" as any]: SPEED_FILL_PCT(fps) }}
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

/** General settings tab — LLM brain config + server + user + paths.
 *
 *  Fetches settings live on mount so this tab always reflects the current
 *  server state — e.g. after saving a new API key via SecretsTab, this
 *  tab immediately shows "✓ configured" instead of a stale prop value.
 */
export function GeneralTab({ settings: propSettings }: { settings?: Settings | null }) {
  const [settings, setSettings] = useState<Settings | null>(propSettings ?? null);
  const [loading, setLoading] = useState(propSettings == null);

  useEffect(() => {
    if (propSettings) {
      setSettings(propSettings);
      return;
    }
    api.getSettings()
      .then(setSettings)
      .catch((e) => toast.error("Failed to load settings", { description: String(e) }))
      .finally(() => setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading || !settings) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading settings...</p>
        </div>
      </HudCard>
    );
  }

  // Non-null assertion for the remainder of the render
  const s = settings;

  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        General
      </h3>

      <Section title="LLM (Brain)">
        <KV label="Provider" value={s.llm.provider} />
        <KV label="Base URL" value={s.llm.base_url} mono />
        <KV label="Default Model" value={s.llm.default_model} accent />
        <KV label="Fallback Model" value={s.llm.fallback_model} />
        <KV
          label="API Key"
          value={s.llm.api_key_configured ? "✓ configured" : "✗ not configured"}
          accent={s.llm.api_key_configured}
          danger={!s.llm.api_key_configured}
        />
      </Section>

      <Section title="Server">
        <KV label="Host" value={s.server.host} mono />
        <KV label="Port" value={String(s.server.port)} mono />
        <KV label="Log Level" value={s.server.log_level} />
        <KV
          label="Tailscale Required"
          value={s.server.require_tailscale ? "yes" : "no"}
        />
        <KV
          label="Tailscale Hostname"
          value={s.server.tailscale_hostname}
          mono
        />
      </Section>

      <Section title="User">
        <KV label="Name" value={s.user.name} />
        <KV label="Default Theme" value={s.user.default_theme} />
      </Section>

      <Section title="Paths">
        <KV label="HALO_HOME" value={s.app.home} mono />
        <KV
          label="Config File"
          value={s.app.config_path}
          mono
          hint="Edit TOML to change settings; restart server to apply"
        />
        <KV label="Version" value={s.app.version} mono />
      </Section>

      <Section title="Tray Icon Animation">
        {isTauriRuntime() ? (
          <TraySpeedControl />
        ) : (
          <p className="text-[10px] text-[var(--text-muted)] font-mono">
            Tray animation controls are only available in the Tauri
            desktop app. (Web dashboard preview.)
          </p>
        )}
      </Section>
    </HudCard>
  );
}
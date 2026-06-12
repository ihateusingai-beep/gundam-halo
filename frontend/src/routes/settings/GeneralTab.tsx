import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import {
  getAnimationSpeed,
  setAnimationSpeed,
} from "@/services/halo-tray-controls";
import type { Settings } from "@/types/api";

import { SPEED_PRESETS } from "./constants";
import { KV, Section } from "./shared";

const SPEED_FILL_PCT = (fps: number | null): string => {
  if (fps == null) return "25%";
  return `${((fps - 1) / 59) * 100}%`;
};

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

export function GeneralTab({ settings }: { settings: Settings }) {
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
        <KV
          label="Tailscale Hostname"
          value={settings.server.tailscale_hostname}
          mono
        />
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

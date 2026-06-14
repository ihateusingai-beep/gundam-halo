import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";
import type { Settings } from "@/types/api";

import { ChannelsTab } from "./ChannelsTab";
import { GeneralTab } from "./GeneralTab";
import { MacTab } from "./MacTab";
import { MemoryTab } from "./MemoryTab";
import { SecretsTab } from "./SecretsTab";
import { SecurityTab } from "./SecurityTab";
import { SETTINGS_TABS, type SettingsTab } from "./constants";
import { ThemesTab } from "./ThemesTab";
import { VoiceTab } from "./VoiceTab";

/** Settings page — 7 tabs: General / Mac / Channels / Themes / Security / Secrets / Memory. */
export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("general");
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
          {SETTINGS_TABS.map((t) => (
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
      {activeTab === "voice" && <VoiceTab />}
    </div>
  );
}

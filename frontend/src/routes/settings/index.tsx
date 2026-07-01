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
import { SettingsSidebar } from "./SettingsSidebar";
import type { SettingsTab } from "./constants";
import { ThemesTab } from "./ThemesTab";
import { VoiceTab } from "./VoiceTab";

/** Settings page — 8 tabs grouped into Personalisation + System (Sprint 50). */
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
    <div
      className="flex h-full"
      data-testid="settings-page"
    >
      {/* Sprint 50: vertical sidebar nav replaces the horizontal
          8-tab bar. Saves horizontal space + handles overflow at
          1024px viewports (where "Security" + "Voice" tabs were
          getting clipped). */}
      <SettingsSidebar active={activeTab} onChange={setActiveTab} />

      {/* Tab content. flex-1 so the sidebar eats 240px (or 48px
          collapsed) and the content fills the rest. */}
      <div className="flex-1 p-4 space-y-3 overflow-y-auto">
        {activeTab === "general" && <GeneralTab settings={settings} />}
        {activeTab === "mac" && <MacTab settings={settings} />}
        {activeTab === "channels" && <ChannelsTab settings={settings} />}
        {activeTab === "themes" && <ThemesTab />}
        {activeTab === "security" && <SecurityTab />}
        {activeTab === "secrets" && <SecretsTab />}
        {activeTab === "memory" && <MemoryTab />}
        {activeTab === "voice" && <VoiceTab />}
      </div>
    </div>
  );
}

import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { openPalette } from "@/components/gundam/CommandPalette";
import { api, ApiError } from "@/lib/api";
import type { Settings } from "@/types/api";

import { ChannelsTab } from "./ChannelsTab";
import { GeneralTab } from "./GeneralTab";
import { MacTab } from "./MacTab";
import { MemoryTab } from "./MemoryTab";
import { SecretsTab } from "./SecretsTab";
import { SecurityTab } from "./SecurityTab";
import { SettingsSidebar } from "./SettingsSidebar";
import { isValidSettingsTab, type SettingsTab } from "./constants";
import { ThemesTab } from "./ThemesTab";
import { VoiceTab } from "./VoiceTab";

/** Settings page — 8 tabs grouped into Personalisation + System (Sprint 50).
 *  Sprint 51: URL ?tab=<id> sync + ⌘K button to open CommandPalette pre-filtered
 *  to the Settings category. */
export function SettingsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const initialTab: SettingsTab = isValidSettingsTab(tabFromUrl) ? tabFromUrl : "general";

  const [activeTab, setActiveTab] = useState<SettingsTab>(initialTab);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Sync state when URL changes externally (e.g. palette deep-link).
  // We only update state if the URL tab differs from current — avoids
  // loops with handleSetActiveTab.
  useEffect(() => {
    const urlTab = searchParams.get("tab");
    if (urlTab && isValidSettingsTab(urlTab) && urlTab !== activeTab) {
      setActiveTab(urlTab);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Centralized tab switch — keeps state + URL in lockstep.
  const handleSetActiveTab = useCallback(
    (tab: SettingsTab) => {
      setActiveTab(tab);
      setSearchParams({ tab }, { replace: true });
    },
    [setSearchParams],
  );

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
      <SettingsSidebar active={activeTab} onChange={handleSetActiveTab} />

      {/* Tab content. flex-1 so the sidebar eats 240px (or 48px
          collapsed) and the content fills the rest. Sprint 51:
          header row with ⌘K button to open CommandPalette pre-filtered
          to Settings category for cross-tab search. */}
      <div className="flex-1 p-4 space-y-3 overflow-y-auto">
        <div className="flex items-center justify-between mb-1" data-testid="settings-header">
          <span className="text-[10px] font-[Rajdhani] uppercase tracking-widest text-[var(--text-muted)]">
            {activeTab}
          </span>
          <button
            type="button"
            data-testid="settings-search-button"
            onClick={() => openPalette({ category: "Settings" })}
            aria-label="Search settings (Cmd+K)"
            aria-keyshortcuts="Meta+K Control+K"
            title="Search settings (⌘K)"
            className="w-8 h-8 flex items-center justify-center rounded text-xs font-mono
                       text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--bg-overlay)]
                       border border-[var(--border-color)]"
          >
            ⌘K
          </button>
        </div>
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

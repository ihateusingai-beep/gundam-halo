import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { openPalette } from "@/components/gundam/CommandPalette";
import { api, ApiError } from "@/lib/api";
import type { Settings } from "@/types/api";

import { ChannelsTab } from "./tabs/ChannelsTab";
import { GeneralTab } from "./tabs/GeneralTab";
import { MacTab } from "./tabs/MacTab";
import { MemoryTab } from "./tabs/MemoryTab";
import { SecretsTab } from "./tabs/SecretsTab";
import { SecurityTab } from "./tabs/SecurityTab";
import { SettingsSidebar } from "./SettingsSidebar";
import { isValidSettingsTab, type SettingsTab } from "./constants";
import { ThemesTab } from "./tabs/ThemesTab";
import { VoiceTab } from "./tabs/VoiceTab";

/** Settings page — 8 tabs grouped into Personalisation + System (Sprint 50).
 *  Sprint 51: URL ?tab=<id> sync + ⌘K button to open CommandPalette pre-filtered
 *  to the Settings category.
 *  Sprint 56 R3: tab rendering uses a `TAB_PANELS` map instead of an
 *  if/else chain — Sprint 56 audit flagged the 8-arm if/else chain as
 *  boilerplate-with-no-single-source-of-truth. The map lives below
 *  alongside the page so adding a 9th tab = adding an entry to
 *  `SIDEBAR_ENTRIES`, `TAB_PANELS`, and `SettingsTab` type. */
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
        <ActiveTabPanel id={activeTab} settings={settings} />
      </div>
    </div>
  );
}

/** Sprint 56 R3: thin wrapper that picks the right panel from
 * `TAB_PANELS`. Splits the if/else chain out of `SettingsPage`'s
 * render block so future tabs only require a single `TAB_PANELS`
 * entry + the panel file under `./tabs/`.
 *
 * Why not a lookup at the call site? Keeping the if/else hidden
 * here (vs in `SettingsPage`'s render) lets the panel tree stay
 * a single component for the React devtools tree, AND keeps
 * `SettingsPage` declarative.
 */
function ActiveTabPanel({
  id,
  settings,
}: {
  id: SettingsTab;
  settings: Settings;
}) {
  const Panel = TAB_PANELS[id];
  return <Panel settings={settings} />;
}

/** Sprint 56 R3: single source of truth for "which panel renders
 * which tab id". Adding a 9th tab = add entry here + entry in
 * `SIDEBAR_ENTRIES` + entry in `SettingsTab` type union. The
 * constants.ts file already has a TypeScript helper
 * (`isValidSettingsTab`) that invalidates the URL ?tab=foo guard
 * automatically once the tab is removed from `SIDEBAR_ENTRIES`.
 */
const TAB_PANELS: Record<SettingsTab, React.ComponentType<{ settings: Settings }>> = {
  general: GeneralTab,
  mac: MacTab,
  channels: ChannelsTab,
  themes: () => <ThemesTab />,
  security: () => <SecurityTab />,
  secrets: () => <SecretsTab />,
  memory: () => <MemoryTab />,
  voice: () => <VoiceTab />,
};

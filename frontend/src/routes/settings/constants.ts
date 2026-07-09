import type { CockpitBackground } from "@/stores/theme";

export type SettingsTab =
  | "general"
  | "mac"
  | "channels"
  | "themes"
  | "security"
  | "secrets"
  | "memory"
  | "voice";

export const SETTINGS_TABS: Array<{ id: SettingsTab; label: string; icon: string }> = [
  { id: "general", label: "General", icon: "◈" },
  { id: "mac", label: "Mac Control", icon: "⚙" },
  { id: "channels", label: "Channels", icon: "◉" },
  { id: "themes", label: "Themes", icon: "◐" },
  { id: "security", label: "Security", icon: "⛨" },
  { id: "secrets", label: "Secrets", icon: "⚿" },
  { id: "memory", label: "User Memory", icon: "▣" },
  { id: "voice", label: "Voice", icon: "◍" },
];

/**
 * Sprint 51 — sidebar entries grouped for the desktop Settings sidebar
 * and the mobile SettingsDrawer. Source of truth for both surfaces.
 * Order matters: rendered top-to-bottom in each group.
 */
export interface SidebarEntry {
  id: SettingsTab;
  label: string;
  icon: string;
  group: "personalisation" | "system";
}

export const SIDEBAR_ENTRIES: SidebarEntry[] = [
  // Personalisation
  { id: "general", label: "General", icon: "◈", group: "personalisation" },
  { id: "voice", label: "Voice", icon: "◍", group: "personalisation" },
  { id: "themes", label: "Themes", icon: "◐", group: "personalisation" },
  { id: "memory", label: "User Memory", icon: "▣", group: "personalisation" },
  // System
  { id: "security", label: "Security", icon: "⛨", group: "system" },
  { id: "mac", label: "Mac Control", icon: "⚙", group: "system" },
  { id: "secrets", label: "Secrets", icon: "⚿", group: "system" },
  { id: "channels", label: "Channels", icon: "◉", group: "system" },
];

/**
 * Sprint 51 — validator for SettingsTab strings from URL params, localStorage,
 * or any other untrusted source. Used by SettingsPage and MobileLayout.
 */
export function isValidSettingsTab(s: string | null | undefined): s is SettingsTab {
  return !!s && SIDEBAR_ENTRIES.some(e => e.id === s);
}

/**
 * Sprint 58 — per-theme bg helpers. Re-exported from
 * `lib/theme-bg-constants.ts` (the single source of truth)
 * so wizard + settings + store all import the same mapping.
 * The `setTheme()` store action auto-cascades the cockpit
 * background to `defaultBgForTheme()` when the user picks a
 * new theme and the current bg is "none" or "core-01" (the
 * historical defaults). Picking SEED no longer leaves you
 * looking at Unicorn NT-D background art.
 */
export {
  defaultBgForTheme,
  resolveBgAsset,
  THEME_DEFAULT_BG,
  THEMES_WITH_BG_SET,
} from "@/lib/theme-bg-constants";

export interface BgOption {
  id: CockpitBackground;
  label: string;
  description: string;
  /** Legacy NT-D Unicorn thumb; the per-theme variant is
   *  computed at render time via `resolveBgAsset(id, themeId)`. */
  thumb: string | null;
}

/** Static descriptor list. The thumbnail URL uses the NT-D
 *  Unicorn baseline; the actual rendered thumb comes from
 *  `resolveBgAsset(id, themeId)` so each theme shows its own
 *  artwork in the wizard. */
export const BACKGROUNDS: BgOption[] = [
  { id: "none", label: "NONE", description: "Pure hex grid — fast, no asset", thumb: null },
  { id: "core-01", label: "CORE-01", description: "Hero — flagship artwork", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg" },
  { id: "core-02", label: "CORE-02", description: "Alternate 1", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-02.jpg" },
  { id: "core-03", label: "CORE-03", description: "Alternate 2", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-03.jpg" },
  { id: "core-04", label: "CORE-04", description: "Alternate 3", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-04.jpg" },
];

export const SPEED_PRESETS: Array<{
  fps: number;
  label: string;
  description: string;
}> = [
  { fps: 8, label: "Battery Saver", description: "8 FPS — minimal visual noise" },
  { fps: 15, label: "Default", description: "15 FPS — smooth, low CPU" },
  { fps: 24, label: "Cinema", description: "24 FPS — animation feels alive" },
];

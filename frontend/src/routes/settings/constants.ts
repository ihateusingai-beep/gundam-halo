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

export interface BgOption {
  id: CockpitBackground;
  label: string;
  description: string;
  thumb: string | null;
}

export const BACKGROUNDS: BgOption[] = [
  { id: "none", label: "NONE", description: "Pure hex grid — fast, no asset", thumb: null },
  { id: "core-01", label: "CORE-01", description: "Psychoframe — pink pulse", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-01.jpg" },
  { id: "core-02", label: "CORE-02", description: "Psychoframe — cyan glow", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-02.jpg" },
  { id: "core-03", label: "CORE-03", description: "Psychoframe — strong pulse", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-03.jpg" },
  { id: "core-04", label: "CORE-04", description: "Psychoframe — soft glow", thumb: "/gundam-assets/backgrounds/bg-unicorn-core-04.jpg" },
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

import { HudCard } from "@/components/gundam/HudCard";
import type { Settings } from "@/types/api";

import { KV, PathList, Section, Toggle } from "../shared";

export function MacTab({ settings }: { settings: Settings }) {
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

import { HudCard } from "@/components/gundam/HudCard";
import { StatusDot } from "@/components/gundam/StatusDot";
import type { Settings } from "@/types/api";

import { KV, Section } from "../shared";

export function ChannelsTab({ settings }: { settings: Settings }) {
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
          value={
            settings.telegram.bot_token_configured
              ? "✓ configured"
              : "✗ not configured"
          }
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
          Configure in <code>~/.gundam-halo/config.toml</code> under{" "}
          <code>[telegram]</code>.
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

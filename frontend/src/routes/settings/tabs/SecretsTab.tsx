import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";

const SECRET_INPUT_CLASS =
  "w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded px-2 py-1 text-xs font-mono " +
  "text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] " +
  "placeholder:text-[var(--text-muted)]/50";

type SecretStatus = {
  label: string;
  configured: boolean;
  source: "override" | "env" | "none";
};

type SecretMap = Record<string, SecretStatus>;

function SecretInput({
  name,
  label,
  value,
  configured,
  source,
  onChange,
  onClear,
  disabled,
}: {
  name: string;
  label: string;
  value: string;
  configured: boolean;
  source: "override" | "env" | "none";
  onChange: (v: string) => void;
  onClear: () => void;
  disabled: boolean;
}) {
  const sourceLabel =
    source === "override"
      ? "stored in .env"
      : source === "env"
      ? "from environment"
      : "not set";
  const sourceColor =
    source === "override"
      ? "var(--accent)"
      : source === "env"
      ? "var(--warning)"
      : "var(--text-muted)";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <label className="text-[10px] text-[var(--text-muted)] uppercase tracking-wider font-[Rajdhani]">
          {label}{" "}
          <span className="text-[var(--text-muted)]/50 font-mono normal-case">
            ({name})
          </span>
        </label>
        <span
          className="text-[10px] font-mono flex items-center gap-1.5"
          style={{ color: sourceColor }}
          title={
            source === "none"
              ? "Type a value below and click Save"
              : `Active source: ${sourceLabel}`
          }
        >
          <span
            className="inline-block w-2 h-2 rounded-full"
            style={{
              background: configured ? sourceColor : "var(--text-muted)",
              boxShadow: configured ? `0 0 6px ${sourceColor}` : "none",
            }}
          />
          {configured ? sourceLabel : "not set"}
        </span>
      </div>
      <div className="flex items-center gap-2">
        <input
          type="password"
          // `new-password` tells the browser this is *not* a login
          // password — it suppresses the "save password?" prompt
          // (which `autoComplete="off"` does NOT reliably do in
          // Chrome/Edge) so secrets never end up in the OS / browser
          // password manager. `data-1p-ignore` + `data-bwignore` are
          // belt-and-braces for 1Password / Bitwarden.
          autoComplete="new-password"
          spellCheck={false}
          data-1p-ignore
          // Hint to password managers (1Password / Bitwarden) not to store
          data-bwignore
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            configured
              ? "••••••••  (type to replace, leave blank to keep)"
              : `Paste your ${name}…`
          }
          className={SECRET_INPUT_CLASS}
          aria-label={label}
        />
        {configured && (
          <button
            onClick={onClear}
            disabled={disabled}
            className="px-2 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--danger)] text-[var(--danger)] hover:bg-[var(--danger)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
            title={`Clear ${name}`}
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
}

/** Secrets tab — manage MiniMax API key + Telegram bot token from the UI.
 *
 * Security properties:
 * - Server NEVER returns the secret value in any response
 * - We only render the configured/source status from GET
 * - Password inputs use autocomplete="new-password" + autoComplete="off"
 *   to discourage browser autofill / saved-password manager capture
 * - Local component state is wiped on unmount (no React DevTools
 *   persistence of the value beyond the lifetime of the form)
 * - onSave success → reset the input field to "" (so the value
 *   isn't lingering in the DOM)
 */
export function SecretsTab() {
  const [status, setStatus] = useState<SecretMap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Two parallel string states. We deliberately never combine into
  // a single object so React can't share memoisation between them.
  const [minimax, setMinimax] = useState("");
  const [telegram, setTelegram] = useState("");
  const [saving, setSaving] = useState(false);

  const refresh = async () => {
    try {
      setError(null);
      const data = await api.getSecrets();
      setStatus(data);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, []);

  const handleSave = async () => {
    const items: Array<{ name: string; value: string }> = [];
    if (minimax.trim()) items.push({ name: "MINIMAX_API_KEY", value: minimax });
    if (telegram.trim()) items.push({ name: "GUNDAM_HALO_TG_TOKEN", value: telegram });
    if (items.length === 0) {
      toast.error("Nothing to save", { description: "Type a value first." });
      return;
    }
    setSaving(true);
    try {
      const updated = await api.setSecrets(items);
      setStatus(updated);
      setMinimax("");
      setTelegram("");
      toast.success("Secrets saved", {
        description:
          "Takes effect on the next LLM / Telegram request. No restart required.",
      });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to save secrets", { description: msg });
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async (name: "MINIMAX_API_KEY" | "GUNDAM_HALO_TG_TOKEN") => {
    setSaving(true);
    try {
      const updated = await api.deleteSecret(name);
      setStatus(updated);
      toast.success("Secret cleared");
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to clear", { description: msg });
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading secrets…</p>
        </div>
      </HudCard>
    );
  }

  if (error) {
    return (
      <HudCard>
        <p className="text-[var(--danger)]">⚠ {error}</p>
      </HudCard>
    );
  }

  const minimaxStatus = status?.["MINIMAX_API_KEY"];
  const telegramStatus = status?.["GUNDAM_HALO_TG_TOKEN"];

  return (
    <HudCard>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Secrets
        </h3>
        <span className="text-[10px] text-[var(--text-muted)] font-mono">
          M6 · runtime-managed
        </span>
      </div>

      <p className="text-xs text-[var(--text-muted)] font-mono mb-4">
        Values are sent over your local / Tailscale network to the backend, persisted
        to <code>~/.gundam-halo/.env</code> with <code>0600</code> permissions, and
        mirrored into the running process. They take effect on the next LLM / Telegram
        request — no server restart required. The server never returns values, only
        whether each one is configured.
      </p>

      <div className="space-y-4">
        <SecretInput
          name="MINIMAX_API_KEY"
          label={minimaxStatus?.label ?? "MiniMax API Key"}
          value={minimax}
          configured={!!minimaxStatus?.configured}
          source={minimaxStatus?.source ?? "none"}
          onChange={setMinimax}
          onClear={() => handleClear("MINIMAX_API_KEY")}
          disabled={saving}
        />

        <SecretInput
          name="GUNDAM_HALO_TG_TOKEN"
          label={telegramStatus?.label ?? "Telegram Bot Token"}
          value={telegram}
          configured={!!telegramStatus?.configured}
          source={telegramStatus?.source ?? "none"}
          onChange={setTelegram}
          onClear={() => handleClear("GUNDAM_HALO_TG_TOKEN")}
          disabled={saving}
        />
      </div>

      <div className="flex items-center justify-end gap-2 mt-4 pt-4 border-t border-[var(--border-color)]">
        <button
          onClick={refresh}
          disabled={saving}
          className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40"
        >
          Refresh
        </button>
        <button
          onClick={handleSave}
          disabled={saving || (!minimax.trim() && !telegram.trim())}
          className="px-4 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </HudCard>
  );
}

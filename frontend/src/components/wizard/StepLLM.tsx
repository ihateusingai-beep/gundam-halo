/**
 * StepLLM — Wizard step 2. Paste LLM API key + provider config.
 *
 * 4 providers, each with its own base URL + default model:
 *   - minimax (default) → https://api.minimax.io/v1, MiniMax-M2
 *   - openai             → https://api.openai.com/v1, gpt-4o-mini
 *   - anthropic          → https://api.anthropic.com/v1, claude-3-5-sonnet
 *   - ollama             → http://localhost:11434/v1, llama3.1
 *
 * Inline validation: clicking "Validate" calls /api/setup/llm/validate
 * (Sprint 44) — does NOT persist. User sees "Key works" or
 * "Key invalid" before clicking Next.
 *
 * Security: we use a password-type input by default with a "Show"
 * toggle. The raw key never appears in the response payload or the
 * network trace after Next is clicked (the backend persists the env
 * var NAME in config.toml, not the key itself).
 */

import { useState } from "react";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { useStepValidation } from "@/hooks/useStepValidation";
import { cn } from "@/lib/utils";
import { setupApi } from "@/lib/setup-api";
import type { LLMConfig } from "@/types/api";
import type { WizardError } from "@/hooks/useSetupWizard";

/** Sprint 63 W-A4 (pilot): Zod schema for the LLM step.
 *  This is the only step migrated in Sprint 63 — the
 *  remaining 6 wizard steps keep their hand-rolled
 *  validation until the pilot proves out. */
const llmSchema = z.object({
  provider: z.enum(["minimax", "openai", "anthropic", "ollama"]),
  api_key: z.string().min(1, "API key is required"),
  base_url: z.string().url("Base URL must be a valid URL"),
  default_model: z.string().min(1, "Default model is required"),
  fallback_model: z.string().optional(),
});

export interface StepLLMProps {
  form: LLMConfig;
  onSubmit: (cfg: LLMConfig) => Promise<void>;
  onValidate: (cfg: LLMConfig) => Promise<{ ok: boolean; model: string | null; error: string | null }>;
  errors: WizardError[];
  busy: boolean;
}

const PROVIDER_DEFAULTS: Record<
  LLMConfig["provider"],
  { base_url: string; default_model: string }
> = {
  minimax: { base_url: "https://api.minimax.io/v1", default_model: "MiniMax-M2" },
  openai: { base_url: "https://api.openai.com/v1", default_model: "gpt-4o-mini" },
  anthropic: { base_url: "https://api.anthropic.com/v1", default_model: "claude-3-5-sonnet-latest" },
  ollama: { base_url: "http://localhost:11434/v1", default_model: "llama3.1" },
};

export function StepLLM({ form, onSubmit, onValidate, errors, busy }: StepLLMProps) {
  const [draft, setDraft] = useState<LLMConfig>(form);
  const [showKey, setShowKey] = useState(false);
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<
    { ok: boolean; message: string } | null
  >(null);

  // Sprint 63 W-A4 (pilot): Zod-backed validation. The hook
  // re-validates on `draft` change (memoised). The result is
  // merged with the parent-supplied `errors` below — backend
  // errors win (they include server-side context like "this
  // key is wrong for THIS model") while Zod errors win on
  // client-side constraints (URL format, non-empty fields).
  const zodValidation = useStepValidation(llmSchema, draft);
  const allErrors: WizardError[] = [
    ...zodValidation.errors.map((e) => ({
      field: e.field,
      code: "zod",
      message: e.message,
    })),
    ...errors,
  ];

  function pickProvider(p: LLMConfig["provider"]) {
    setDraft((d) => ({
      ...d,
      provider: p,
      base_url: PROVIDER_DEFAULTS[p].base_url,
      default_model: PROVIDER_DEFAULTS[p].default_model,
    }));
    setValidation(null);
  }

  async function handleValidate() {
    setValidating(true);
    setValidation(null);
    try {
      const res = await onValidate(draft);
      setValidation({
        ok: res.ok,
        message: res.ok
          ? `✓ Key works (model: ${res.model ?? draft.default_model})`
          : `✗ ${res.error ?? "Invalid key"}`,
      });
    } catch (e) {
      setValidation({ ok: false, message: `Network error: ${String(e)}` });
    } finally {
      setValidating(false);
    }
  }

  async function handleNext() {
    await onSubmit(draft);
  }

  // Highlight errors per field. Zod errors take precedence
  // over backend errors for the same field (Zod catches
  // "URL malformed" before the user clicks Next).
  const errorByField = Object.fromEntries(
    allErrors.map((e) => [e.field, e.message]),
  );

  return (
    <div className="space-y-3 py-2" data-testid="step-llm">
      <h2 className="text-lg font-[Rajdhani] text-[var(--text-primary)]">
        LLM Provider
      </h2>

      <div>
        <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
          Provider
        </label>
        <select
          data-testid="llm-provider"
          value={draft.provider}
          onChange={(e) => pickProvider(e.target.value as LLMConfig["provider"])}
          className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-sm font-mono focus:border-[var(--accent)] outline-none"
        >
          <option value="minimax">MiniMax (M2 / M3 cluster)</option>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
          <option value="ollama">Ollama (local)</option>
        </select>
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
          API Key
        </label>
        <div className="flex gap-2 mt-1">
          <input
            data-testid="llm-api-key"
            type={showKey ? "text" : "password"}
            value={draft.api_key}
            onChange={(e) => {
              setDraft({ ...draft, api_key: e.target.value });
              setValidation(null);
            }}
            placeholder="sk-…"
            className="flex-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-sm font-mono focus:border-[var(--accent)] outline-none"
          />
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowKey((v) => !v)}
            disabled={!draft.api_key}
          >
            {showKey ? "Hide" : "Show"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={handleValidate}
            disabled={!draft.api_key || validating || busy}
            data-testid="llm-validate"
          >
            {validating ? "Checking…" : "Validate"}
          </Button>
        </div>
        {validation && (
          <p
            data-testid="llm-validation"
            className={cn(
              "text-[10px] font-mono mt-1",
              validation.ok ? "text-[var(--accent)]" : "text-[var(--danger)]",
            )}
          >
            {validation.message}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Base URL
          </label>
          <input
            value={draft.base_url}
            onChange={(e) => setDraft({ ...draft, base_url: e.target.value })}
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono focus:border-[var(--accent)] outline-none"
          />
          {errorByField.base_url && (
            <p className="text-[10px] text-[var(--danger)] mt-0.5">
              {errorByField.base_url}
            </p>
          )}
        </div>
        <div>
          <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
            Default Model
          </label>
          <input
            data-testid="llm-default-model"
            value={draft.default_model}
            onChange={(e) => setDraft({ ...draft, default_model: e.target.value })}
            className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono focus:border-[var(--accent)] outline-none"
          />
          {errorByField.default_model && (
            <p className="text-[10px] text-[var(--danger)] mt-0.5">
              {errorByField.default_model}
            </p>
          )}
        </div>
      </div>

      <div>
        <label className="text-[10px] uppercase tracking-widest font-[Orbitron] text-[var(--text-muted)]">
          Fallback Model (optional)
        </label>
        <input
          value={draft.fallback_model ?? ""}
          onChange={(e) => setDraft({ ...draft, fallback_model: e.target.value })}
          placeholder="(leave blank to disable)"
          className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono focus:border-[var(--accent)] outline-none"
        />
      </div>

      <div className="pt-2 flex gap-2">
        <Button
          onClick={handleNext}
          disabled={!draft.api_key || busy}
          data-testid="llm-next"
        >
          {busy ? "Saving…" : "Next →"}
        </Button>
      </div>
    </div>
  );
}

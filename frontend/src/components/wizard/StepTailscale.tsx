/**
 * StepTailscale — Wizard step 6. Optional Tailscale config.
 *
 * Per the project memory: "Tailscale-only access pattern" is the
 * default. This step is OPTIONAL — the user can skip it and the
 * backend will still work (just not be reachable remotely).
 *
 * If the user enables Tailscale, the backend's /api/setup/tailscale
 * handler runs `tailscale ping <hostname>` to verify reachability
 * before marking the step complete.
 */

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { TailscaleConfig } from "@/types/api";
import type { WizardError } from "@/hooks/useSetupWizard";

export interface StepTailscaleProps {
  form: TailscaleConfig;
  onSubmit: (cfg: TailscaleConfig) => Promise<void>;
  errors: WizardError[];
  busy: boolean;
}

export function StepTailscale({ form, onSubmit, errors, busy }: StepTailscaleProps) {
  const [draft, setDraft] = useState<TailscaleConfig>(form);

  return (
    <div className="space-y-3 py-2" data-testid="step-tailscale">
      <h2 className="text-lg font-[Rajdhani] text-[var(--text-primary)]">
        Remote Access (Tailscale)
      </h2>

      <p className="text-[10px] text-[var(--text-muted)] font-mono leading-relaxed">
        Gundam Halo is Tailscale-only — there is no public-internet
        access. To enable remote access (e.g. from your phone or
        another Mac), set up Tailscale first and then come back to
        this step.
      </p>

      <a
        href="https://tailscale.com/download"
        target="_blank"
        rel="noreferrer"
        className="inline-block text-[10px] font-mono text-[var(--accent)] hover:underline"
      >
        Download Tailscale →
      </a>

      <div className="flex items-center gap-2 pt-2">
        <button
          data-testid="tailscale-enable"
          onClick={() => setDraft({ ...draft, enabled: !draft.enabled })}
          className={cn(
            "px-3 py-1 text-xs font-mono border",
            draft.enabled
              ? "border-[var(--accent)] text-[var(--accent)]"
              : "border-[var(--border-color)] text-[var(--text-muted)]",
          )}
        >
          {draft.enabled ? "✓ Enabled" : "Enable Tailscale"}
        </button>
        <input
          data-testid="tailscale-hostname"
          value={draft.hostname}
          onChange={(e) => setDraft({ ...draft, hostname: e.target.value })}
          disabled={!draft.enabled}
          className="flex-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono disabled:opacity-40"
        />
      </div>

      {errors.length > 0 && (
        <p className="text-[10px] text-[var(--danger)] font-mono">
          {errors[0].message}
        </p>
      )}

      <div className="pt-2 flex gap-2">
        <Button
          variant="outline"
          onClick={() =>
            onSubmit({ ...draft, enabled: false })
          }
          disabled={busy}
          data-testid="tailscale-skip"
        >
          Skip for now
        </Button>
        <Button
          onClick={() => onSubmit(draft)}
          disabled={busy || !draft.hostname}
          data-testid="tailscale-next"
        >
          {busy ? "Saving…" : "Next →"}
        </Button>
      </div>
    </div>
  );
}

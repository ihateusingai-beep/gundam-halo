/**
 * StepWelcome — Wizard step 1. Intro + "Let's go" CTA.
 *
 * The step is intentionally minimal — no form fields. The "Let's
 * go" button simply calls onNext() which triggers the backend's
 * /api/setup/start + advances to step 2.
 */

import { Button } from "@/components/ui/button";

export interface StepWelcomeProps {
  onNext: () => void;
}

export function StepWelcome({ onNext }: StepWelcomeProps) {
  return (
    <div className="space-y-4 py-4" data-testid="step-welcome">
      <h2 className="text-xl font-[Rajdhani] text-[var(--text-primary)]">
        Configure Gundam Halo in 7 steps
      </h2>
      <p className="text-sm text-[var(--text-secondary)] font-mono leading-relaxed">
        This wizard sets up your LLM provider, voice pipeline, theme,
        and remote access. Each step takes ~30 seconds. Your data
        stays on this Mac — no cloud sync, no telemetry.
      </p>
      <ul className="text-xs text-[var(--text-secondary)] font-mono space-y-1 list-disc list-inside">
        <li>
          <strong>Step 2</strong> — LLM provider (MiniMax / OpenAI /
          Anthropic / Ollama)
        </li>
        <li>
          <strong>Step 3-4</strong> — Voice ASR + TTS
        </li>
        <li>
          <strong>Step 5</strong> — Pick a theme (8 to choose from)
        </li>
        <li>
          <strong>Step 6</strong> — Tailscale (optional remote access)
        </li>
        <li>
          <strong>Step 7</strong> — Smoke test (text + voice round-trip)
        </li>
      </ul>
      <p className="text-[10px] text-[var(--text-muted)] font-mono">
        You can close this window at any time. Your progress is saved
        automatically — reopening resumes from where you left off.
      </p>
      <div className="pt-2">
        <Button onClick={onNext} data-testid="welcome-lets-go">
          Let's go →
        </Button>
      </div>
    </div>
  );
}

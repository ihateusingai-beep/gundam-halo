/**
 * WizardShell — Sprint 44. Top-level layout for the /setup wizard.
 *
 * Renders the step indicator + the active step component + the
 * Back/Next/Skip navigation footer. All state flows through the
 * useSetupWizard hook; this component is purely presentational.
 *
 * Sprint 74 X-A — progressive disclosure. The wizard now has 2
 * modes:
 *   - `essential` (3 steps: Welcome → LLM → Smoke)
 *   - `advanced`  (7 steps: + Voice ASR, TTS, Theme, Tailscale)
 * The header shows a "Show advanced setup" toggle. StepIndicator
 * renders 3 dots in essential, 7 in advanced. The active step's
 * component is rendered normally; if the user is in essential mode
 * but jumps to an advanced step (e.g. via deep-link), the indicator
 * shows an "Advanced only" hint and prompts to switch modes.
 *
 * Hidden in Tauri dev mode when running outside the Tauri shell —
 * the wizard requires the backend running at $VITE_API_BASE.
 */

import { useCallback, type ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";
import { cn } from "@/lib/utils";

import {
  ADVANCED_TOTAL_STEPS,
  ESSENTIAL_TOTAL_STEPS,
  useSetupWizard,
  type WizardMode,
  type WizardStep,
} from "@/hooks/useSetupWizard";
import { StepFinish } from "@/components/wizard/StepFinish";
import { StepLLM } from "@/components/wizard/StepLLM";
import { StepSmoke } from "@/components/wizard/StepSmoke";
import { StepTailscale } from "@/components/wizard/StepTailscale";
import { StepTheme } from "@/components/wizard/StepTheme";
import { StepVoiceASR } from "@/components/wizard/StepVoiceASR";
import { StepVoiceTTS } from "@/components/wizard/StepVoiceTTS";
import { StepWelcome } from "@/components/wizard/StepWelcome";

const STEP_LABELS: Record<WizardStep, string> = {
  1: "Welcome",
  2: "LLM Provider",
  3: "Voice ASR",
  4: "Voice TTS",
  5: "Theme",
  6: "Tailscale",
  7: "Smoke Test",
};

/** Steps 3-6 are advanced-only. Steps 1, 2, 7 are essential. */
const ESSENTIAL_STEPS: ReadonlySet<WizardStep> = new Set([1, 2, 7]);
const ADVANCED_STEPS: ReadonlySet<WizardStep> = new Set([3, 4, 5, 6]);

function isStepInMode(step: WizardStep, mode: WizardMode): boolean {
  if (mode === "advanced") return true;
  return ESSENTIAL_STEPS.has(step);
}

export function WizardShell() {
  const wizard = useSetupWizard();
  const navigate = useNavigate();

  const handleToggleMode = useCallback(() => {
    const next: WizardMode = wizard.mode === "essential" ? "advanced" : "essential";
    void wizard.setMode(next);
  }, [wizard]);

  if (wizard.status === "loading") {
    return (
      <div className="max-w-3xl mx-auto p-4">
        <HudCard>
          <p className="text-sm text-[var(--text-muted)] font-mono">
            Loading wizard state…
          </p>
        </HudCard>
      </div>
    );
  }

  if (wizard.status === "finished") {
    return <StepFinish redirect={wizard.redirect} onOpenCockpit={() => navigate("/")} />;
  }

  // Defensive: if the persisted state has current_step > totalSteps
  // for the active mode (e.g. user was in advanced, then toggled to
  // essential at step 5), clamp to last essential step.
  const safeStep: WizardStep = isStepInMode(wizard.currentStep, wizard.mode)
    ? wizard.currentStep
    : (7 as WizardStep);

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <header>
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
              Setup Wizard
            </h1>
            <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
              {wizard.mode === "essential"
                ? `${ESSENTIAL_TOTAL_STEPS} essential steps · on-device configuration`
                : `${ADVANCED_TOTAL_STEPS} steps (advanced) · on-device configuration`}
            </p>
          </div>
          {/* Sprint 74 X-A — advanced toggle. Hidden on the very
            * first run (loading state) so a fresh user isn't
            * immediately asked to make a UX choice. */}
          <button
            type="button"
            onClick={handleToggleMode}
            data-testid="wizard-mode-toggle"
            data-current-mode={wizard.mode}
            className="shrink-0 px-3 py-1.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
            title={
              wizard.mode === "essential"
                ? "Reveal the 4 advanced steps (Voice ASR/TTS, Theme, Tailscale)"
                : "Hide advanced steps and use the 3-step fast path"
            }
          >
            {wizard.mode === "essential" ? "Show advanced" : "Hide advanced"}
          </button>
        </div>
      </header>

      {/* Step indicator — renders 3 dots in essential, 7 in advanced */}
      <StepIndicator
        currentStep={safeStep}
        completedSteps={wizard.completedSteps}
        mode={wizard.mode}
      />

      {/* If the user is in essential mode but their persisted
        * current_step is advanced (3-6), show a soft prompt to
        * advance-mode before continuing. */}
      {!isStepInMode(wizard.currentStep, wizard.mode) && (
        <HudCard className="!border-[var(--warning)] !bg-[var(--warning)]/5">
          <div data-testid="advanced-required-hint" className="text-xs font-mono">
            <strong className="text-[var(--warning)]">Step {wizard.currentStep} is an advanced step.</strong>{" "}
            <span className="text-[var(--text-muted)]">
              Switch to advanced mode to continue.
            </span>
          </div>
        </HudCard>
      )}

      {/* Error display (per-field errors from the backend). */}
      {wizard.errors.length > 0 && (
        <HudCard className="!border-[var(--danger)] !bg-[var(--danger)]/5">
          <div data-testid="wizard-errors" className="space-y-1">
            {wizard.errors.map((err, i) => (
              <p
                key={i}
                className="text-xs font-mono text-[var(--danger)]"
                data-field={err.field}
              >
                <strong>{err.field}:</strong> {err.message}
              </p>
            ))}
          </div>
        </HudCard>
      )}

      {/* Active step */}
      <HudCard>
        <div className="min-h-[280px]">
          {renderStep(safeStep, wizard)}
        </div>
      </HudCard>

      {/* Footer: Back / Next / Skip */}
      <StepFooter
        wizard={wizard}
        onSkip={async () => {
          if (
            !window.confirm(
              "Skip the wizard? You'll need to configure ~/.gundam-halo/config.toml manually.",
            )
          ) {
            return;
          }
          await wizard.skip();
        }}
      />

      <p className="text-[10px] text-[var(--text-muted)] font-mono text-center">
        Your data stays on this Mac. Crashes are recovered — close and reopen
        the wizard to resume from where you left off.
      </p>
    </div>
  );
}

function renderStep(step: WizardStep, wizard: ReturnType<typeof useSetupWizard>): ReactNode {
  switch (step) {
    case 1:
      return <StepWelcome onNext={() => wizard.submitLLM(wizard.llmForm)} />;
    case 2:
      return (
        <StepLLM
          form={wizard.llmForm}
          onSubmit={wizard.submitLLM}
          onValidate={wizard.validateLLM}
          errors={wizard.errors}
          busy={wizard.status === "submitting"}
        />
      );
    case 3:
      return (
        <StepVoiceASR
          form={wizard.asrForm}
          onSubmit={wizard.submitASR}
          errors={wizard.errors}
          busy={wizard.status === "submitting"}
        />
      );
    case 4:
      return (
        <StepVoiceTTS
          form={wizard.ttsForm}
          onSubmit={wizard.submitTTS}
          onPreview={wizard.previewTTS}
          errors={wizard.errors}
          busy={wizard.status === "submitting"}
        />
      );
    case 5:
      return (
        <StepTheme
          form={wizard.themeForm}
          onChange={wizard.submitTheme}
          errors={wizard.errors}
          busy={wizard.status === "submitting"}
        />
      );
    case 6:
      return (
        <StepTailscale
          form={wizard.tailscaleForm}
          onSubmit={wizard.submitTailscale}
          errors={wizard.errors}
          busy={wizard.status === "submitting"}
        />
      );
    case 7:
      return <StepSmoke wizard={wizard} />;
    default:
      return <p>Unknown step: {step}</p>;
  }
}

interface StepIndicatorProps {
  currentStep: WizardStep;
  completedSteps: WizardStep[];
  mode: WizardMode;
}

/** The 3 actual wizard steps shown in essential mode. The pilot's
 *  fast path is Welcome (1) → LLM (2) → Smoke (7) — steps 3-6
 *  (Voice ASR/TTS, Theme, Tailscale) are advanced-only and are
 *  NOT shown as indicators in essential mode (skipping 3-6 in
 *  the visual is intentional; the dot for step 7 immediately
 *  follows the dot for step 2). */
const ESSENTIAL_INDICATOR_STEPS: ReadonlyArray<WizardStep> = [1, 2, 7];
const ADVANCED_INDICATOR_STEPS: ReadonlyArray<WizardStep> = [1, 2, 3, 4, 5, 6, 7];

function StepIndicator({ currentStep, completedSteps, mode }: StepIndicatorProps) {
  // Sprint 74 X-A — render the actual step numbers (not renumbered
  // positions) so clicking a step navigates to the right wizard
  // step. In essential mode we show 3 dots: 1, 2, 7. The visual
  // gap between "2. LLM" and "7. Smoke" is intentional.
  const steps = mode === "advanced" ? ADVANCED_INDICATOR_STEPS : ESSENTIAL_INDICATOR_STEPS;
  return (
    <ol className="flex items-center gap-2 text-[10px] font-[Orbitron] uppercase tracking-widest">
      {steps.map((s) => {
        const isDone = completedSteps.includes(s);
        const isCurrent = s === currentStep;
        return (
          <li
            key={s}
            className={cn(
              "flex-1 text-center py-1.5 border-t-2 transition-colors",
              isDone
                ? "text-[var(--accent)] border-[var(--accent)]"
                : isCurrent
                  ? "text-[var(--warning)] border-[var(--warning)]"
                  : "text-[var(--text-muted)] border-[var(--border-color)]",
            )}
            data-testid={`step-indicator-${s}`}
            data-state={
              isDone ? "done" : isCurrent ? "current" : "pending"
            }
            data-mode={mode}
          >
            {s}. {STEP_LABELS[s]}
          </li>
        );
      })}
    </ol>
  );
}

interface StepFooterProps {
  wizard: ReturnType<typeof useSetupWizard>;
  onSkip: () => void;
}

function StepFooter({ wizard, onSkip }: StepFooterProps) {
  const isSubmitting = wizard.status === "submitting";
  // Back is only useful from step 2 onwards.
  const showBack = wizard.currentStep > 1;

  return (
    <div className="flex items-center justify-between gap-2 flex-wrap">
      <div className="flex gap-2">
        {showBack && (
          <button
            disabled
            className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] opacity-50 cursor-not-allowed"
            title="Back navigation disabled in v1 (each step is self-contained)"
          >
            ← Back
          </button>
        )}
        <button
          onClick={onSkip}
          disabled={isSubmitting}
          className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors disabled:opacity-40"
        >
          Skip wizard
        </button>
      </div>
      <Link
        to="/"
        className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors"
      >
        ← Back to cockpit
      </Link>
    </div>
  );
}

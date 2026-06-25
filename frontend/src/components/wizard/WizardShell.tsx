/**
 * WizardShell — Sprint 44. Top-level layout for the /setup wizard.
 *
 * Renders the step indicator + the active step component + the
 * Back/Next/Skip navigation footer. All state flows through the
 * useSetupWizard hook; this component is purely presentational.
 *
 * Hidden in Tauri dev mode when running outside the Tauri shell —
 * the wizard requires the backend running at $VITE_API_BASE.
 */

import type { ReactNode } from "react";
import { Link, useNavigate } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";
import { cn } from "@/lib/utils";

import { useSetupWizard, type WizardStep } from "@/hooks/useSetupWizard";
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

export function WizardShell() {
  const wizard = useSetupWizard();
  const navigate = useNavigate();

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

  return (
    <div className="max-w-3xl mx-auto p-4 space-y-4">
      <header>
        <h1 className="text-2xl font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Setup Wizard
        </h1>
        <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
          7 steps · on-device configuration
        </p>
      </header>

      {/* Step indicator */}
      <StepIndicator
        currentStep={wizard.currentStep}
        completedSteps={wizard.completedSteps}
      />

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
          {renderStep(wizard.currentStep, wizard)}
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
}

function StepIndicator({ currentStep, completedSteps }: StepIndicatorProps) {
  return (
    <ol className="flex items-center gap-2 text-[10px] font-[Orbitron] uppercase tracking-widest">
      {([1, 2, 3, 4, 5, 6, 7] as WizardStep[]).map((s) => {
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

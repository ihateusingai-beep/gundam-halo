/**
 * HowItWorksSection — explanatory paragraph.
 *
 * Extracted from VoiceTab.tsx (Sprint 56.7). Pure prose,
 * no interactions. Lives at the bottom of the tab to give
 * the user a quick reference for what strict-mode does and
 * when to switch it off.
 */
import { Section } from "../../../shared";

export function HowItWorksSection() {
  return (
    <Section title="How it works">
      <p className="text-xs text-[var(--text-muted)] font-mono leading-relaxed">
        Strict mode (on by default in Sprint 17a) is the recommended
        setting: it stops background TV and accidental mic-button
        bumps from invoking the agent. Permissive mode is useful
        for keyboard-driven debug sessions where you want every
        transcript to reach the agent. The wake phrase list above
        applies in both modes; in strict mode the prefix is
        required, in permissive mode it's a confidence marker.
      </p>
    </Section>
  );
}

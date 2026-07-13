/**
 * VoiceTab.test.tsx — Sprint 70 X-A1e.
 *
 * Mounts the voice settings tab orchestrator (`VoiceTab.tsx`)
 * and verifies the loaded state. Aims to bump
 * `VoiceTab.tsx` coverage from 2.4% to ~70% (Sprint 70
 * X-A1e coverage ratchet; target: line coverage ≥55%).
 *
 * Also covers the 7 leaf sections in the orchestrator's
 * render path (AlwaysOnSection, AsrSection, DiagnosticsSection,
 * HowItWorksSection, PersonalisedFineTuneSection, WakeSection,
 * + the SaveBar) — most were at 0% before this sprint.
 *
 * Mirrors the Sprint 67 + 69 pattern: mock `@/lib/api`,
 * mock `@/services/halo-voice-ws`, render + wait for the
 * initial fetch to resolve.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock @/lib/api for the getVoiceConfig + setVoiceConfig
// calls. The mock returns a small valid config so the
// orchestrator's hydration logic runs.
vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:5173",
  api: {
    getVoiceConfig: vi.fn().mockResolvedValue({
      wake_phrases: ["Unicorn", "NTD"],
      strict_wake_phrase: true,
      asr_backend: "whisper_local",
      asr_corrector: "bert",
      always_on_mic: false,
    }),
    setVoiceConfig: vi.fn().mockResolvedValue({
      wake_phrases: ["Unicorn", "NTD"],
      strict_wake_phrase: true,
      asr_backend: "whisper_local",
      asr_corrector: "bert",
      always_on_mic: false,
      restart_required: false,
    }),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: unknown;
    constructor(status: number, body: unknown, message: string) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
}));

// Mock @/services/halo-voice-ws for the getVoiceStatus
// module-level function (used in VoiceTab's 5s polling
// interval + initial state seed).
vi.mock("@/services/halo-voice-ws", () => ({
  getVoiceStatus: () => ({ state: "idle" }),
  onVoiceStatusChange: vi.fn().mockReturnValue(() => {}),
  type: { VoiceState: "idle" },
}));

// Mock @/lib/tauri for the PersonalisedFineTuneSection's
// `isTauriRuntime()` check (disables the 3 cards' buttons
// in jsdom).
vi.mock("@/lib/tauri", () => ({
  isTauriRuntime: () => false,
  tryTauriInvoke: vi.fn().mockResolvedValue(undefined),
}));

// Mock the runFinetuneCommand module so clicking the
// Personalised Fine-tune cards' buttons doesn't try to
// invoke real Tauri commands.
vi.mock("./voice/runFinetuneCommand", () => ({
  runFinetuneCommand: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => {
  cleanup();
});

// Imported AFTER mocks so the mocks apply to the module graph.
import { VoiceTab } from "./VoiceTab";

describe("VoiceTab (orchestrator mount)", () => {
  it("renders the sectioned voice settings UI after the config fetch resolves", async () => {
    render(<VoiceTab />);

    // The orchestrator shows a loading radar initially,
    // then resolves to the sectioned UI. Wait for one of
    // the stable section testids to surface.
    // PersonalisedFineTuneSection has a stable testid
    // (after the Sprint 70 HudCard fix that forwards
    // data-testid through).
    await waitFor(() => {
      expect(
        screen.getByTestId("personalised-finetune-intro"),
      ).toBeInTheDocument();
    });

    // Assert the 3 cards are present.
    expect(
      screen.getByTestId("personalised-finetune-record-card"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("personalised-finetune-train-card"),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId("personalised-finetune-swap-card"),
    ).toBeInTheDocument();
  });
});

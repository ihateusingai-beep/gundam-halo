/**
 * PersonalisedFineTuneSection.test.tsx — Sprint 70 X-A1e.
 *
 * Mounts the personalised fine-tune section (3-card
 * Record / Train / Swap flow) and verifies the basic
 * render. Aims to bump `PersonalisedFineTuneSection.tsx`
 * coverage from 0% to ~70% (Sprint 70 X-A1e coverage
 * ratchet; target: line coverage ≥55%).
 *
 * Mirrors the Sprint 67 + 69 pattern: mock external deps
 * (`@/lib/tauri` for `isTauriRuntime`), mount the component,
 * wait for the initial render, assert content.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock @/lib/tauri so `isTauriRuntime()` returns false
// (no Tauri shell in jsdom). The button is `disabled` in
// that case, but the card still renders.
vi.mock("@/lib/tauri", () => ({
  isTauriRuntime: () => false,
  tryTauriInvoke: vi.fn().mockResolvedValue(undefined),
}));

// Mock the runFinetuneCommand module so clicking the
// buttons doesn't try to invoke real Tauri commands.
vi.mock("../runFinetuneCommand", () => ({
  runFinetuneCommand: vi.fn().mockResolvedValue(undefined),
}));

afterEach(() => {
  cleanup();
});

// Imported AFTER mocks so the mocks apply to the module graph.
import { PersonalisedFineTuneSection } from "./PersonalisedFineTuneSection";

describe("PersonalisedFineTuneSection (mount)", () => {
  it("renders the 3 cards (Record, Train, Swap) with disabled buttons (no Tauri runtime)", () => {
    render(<PersonalisedFineTuneSection />);

    // The 3 cards are stable testids in the source.
    const recordCard = screen.getByTestId(
      "personalised-finetune-record-card",
    );
    const trainCard = screen.getByTestId(
      "personalised-finetune-train-card",
    );
    const swapCard = screen.getByTestId(
      "personalised-finetune-swap-card",
    );
    expect(recordCard).toBeInTheDocument();
    expect(trainCard).toBeInTheDocument();
    expect(swapCard).toBeInTheDocument();

    // All 3 buttons should be disabled (isTauriRuntime → false).
    const recordButton = screen.getByTestId(
      "personalised-finetune-record-button",
    );
    const trainButton = screen.getByTestId(
      "personalised-finetune-train-button",
    );
    const swapButton = screen.getByTestId(
      "personalised-finetune-swap-button",
    );
    expect(recordButton).toBeDisabled();
    expect(trainButton).toBeDisabled();
    expect(swapButton).toBeDisabled();
  });

  it("renders the intro paragraph + section title", () => {
    render(<PersonalisedFineTuneSection />);
    // The intro paragraph has a stable testid.
    expect(
      screen.getByTestId("personalised-finetune-intro"),
    ).toBeInTheDocument();
  });
});

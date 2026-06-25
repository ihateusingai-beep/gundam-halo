/**
 * VoiceWsIndicator.test.tsx — Sprint 39 Track B acceptance test.
 *
 * Verifies the pill renders the right label + `data-state` for the
 * `reconnecting` value (the most visually distinct state — pink
 * dot + "RECONNECTING" label). Other states follow the same shape;
 * we don't duplicate tests for all 7 values.
 *
 * Mocking strategy:
 *   - `@/services/halo-voice-ws::getVoiceStatus` is mocked so the
 *     component reads a known snapshot on first poll. The 2s
 *     interval is not exercised in this test (no fake timers).
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const getVoiceStatusMock = vi.fn();
vi.mock("@/services/halo-voice-ws", () => ({
  getVoiceStatus: (...args: unknown[]) => getVoiceStatusMock(...args),
}));

import { VoiceWsIndicator } from "@/components/dashboard/VoiceWsIndicator";

afterEach(() => {
  getVoiceStatusMock.mockReset();
  cleanup();
});

describe("VoiceWsIndicator", () => {
  it("renders the reconnecting state with pink pill + RECONNECTING label", () => {
    getVoiceStatusMock.mockReturnValue({
      state: "reconnecting",
      lastAsr: "try the cockpit",
      serverEnabled: true,
      error: null,
    });

    render(<VoiceWsIndicator />);

    const card = screen.getByTestId("voice-ws-indicator");
    expect(card.getAttribute("data-state")).toBe("reconnecting");

    // The label appears verbatim — uppercase per STATE_LABELS.
    expect(card.textContent).toContain("RECONNECTING");

    // The pilot's last transcript is surfaced for debug.
    expect(card.textContent).toContain("try the cockpit");
  });
});

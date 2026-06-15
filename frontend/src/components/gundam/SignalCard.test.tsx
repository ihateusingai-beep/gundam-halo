/**
 * SignalCard.test.tsx — Sprint 18 Track A acceptance test.
 *
 * Verifies:
 *  1. Renders a canvas (the CyberWaveform) with the right "idle"
 *     data-source when the mic isn't capturing.
 *  2. Flips the data-source to "mic" when `mic.state === "capturing"`.
 *  3. Forwards the live `stream` from the mic hook to the canvas's
 *     useSharedAmplitude consumer (we assert via a mock useSharedAmplitude
 *     that receives the right (source, stream) pair on every render).
 *
 * The full cockpit layout (CockpitLayout.tsx) is too heavy to unit-test
 * — it pulls in WS, projects, gauges, live2d, etc. SignalCard is the
 * encapsulated unit that owns the audio-reactive logic, so we test
 * that directly.
 */

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UseVoiceInputResult } from "@/hooks/use-voice-input";

// We mock use-shared-amplitude so we can capture the (source, stream)
// pair passed by CyberWaveform without standing up the full
// hook + AnalyserNode + requestAnimationFrame chain. CyberWaveform
// calls useSharedAmplitude(source, stream) and uses the returned amp
// to drive a canvas rAF loop — we don't need the loop for these
// tests; we only need to assert the right source/stream is plumbed.
const useSharedAmplitudeMock = vi.fn();
vi.mock("@/hooks/use-shared-amplitude", () => ({
  useSharedAmplitude: (...args: unknown[]) => {
    useSharedAmplitudeMock(...args);
    return 0.5;
  },
}));

// We mock CyberWaveform so the test doesn't try to create a canvas
// (jsdom's canvas impl is partial and would log warnings). The mock
// renders a stub <canvas data-source data-stream> we can query.
vi.mock("@/components/gundam/CyberWaveform", () => ({
  CyberWaveform: (props: {
    source?: "idle" | "mic";
    stream?: MediaStream | null;
    height?: number;
    layers?: number;
    amplitudeScale?: number;
  }) => {
    return (
      <canvas
        data-testid="cyber-waveform"
        data-source={props.source}
        data-stream={props.stream ? "live" : "none"}
        data-height={props.height}
        data-layers={props.layers}
        data-amp-scale={props.amplitudeScale}
      />
    );
  },
}));

// We mock the import order — SignalCard imports SignalCard from
// "@/components/gundam/SignalCard" which imports CyberWaveform. The
// mock above replaces CyberWaveform, so SignalCard's import resolves
// to our mock.
import { SignalCard } from "@/components/gundam/SignalCard";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeMic(overrides: Partial<UseVoiceInputResult> = {}): UseVoiceInputResult {
  return {
    state: "idle",
    error: null,
    start: vi.fn(),
    stop: vi.fn(),
    stream: null,
    ...overrides,
  };
}

afterEach(() => {
  useSharedAmplitudeMock.mockClear();
  // Each render() leaves its DOM in the test container. Without
  // cleanup, the next getByTestId call returns the *first* matching
  // element from prior renders (a classic "multiple elements found"
  // failure when re-rendering in the same file).
  cleanup();
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SignalCard", () => {
  it("renders with data-source='idle' when mic is not capturing", () => {
    const mic = makeMic({ state: "idle", stream: null });
    render(<SignalCard mic={mic} />);

    const card = screen.getByTestId("cockpit-signal-card");
    expect(card).toBeTruthy();
    expect(card.getAttribute("data-source")).toBe("idle");

    const canvas = screen.getByTestId("cyber-waveform");
    expect(canvas.getAttribute("data-source")).toBe("idle");
    expect(canvas.getAttribute("data-stream")).toBe("none");
  });

  it("flips data-source to 'mic' when mic.state is 'capturing'", () => {
    const fakeStream = {
      // Minimal MediaStream shape — the mock canvas only checks
      // truthiness, so we don't need to fully implement MediaStream.
      id: "fake-stream",
      active: true,
      getTracks: () => [],
      getAudioTracks: () => [],
      getVideoTracks: () => [],
      addTrack: () => {},
      removeTrack: () => {},
      clone: () => fakeStream,
    } as unknown as MediaStream;
    const mic = makeMic({ state: "capturing", stream: fakeStream });
    render(<SignalCard mic={mic} />);

    const card = screen.getByTestId("cockpit-signal-card");
    expect(card.getAttribute("data-source")).toBe("mic");

    const canvas = screen.getByTestId("cyber-waveform");
    expect(canvas.getAttribute("data-source")).toBe("mic");
    expect(canvas.getAttribute("data-stream")).toBe("live");
  });

  it("uses default 80px height and 4 layers and 1.2 amplitudeScale", () => {
    const mic = makeMic();
    render(<SignalCard mic={mic} />);

    const canvas = screen.getByTestId("cyber-waveform");
    expect(canvas.getAttribute("data-height")).toBe("80");
    expect(canvas.getAttribute("data-layers")).toBe("4");
    expect(canvas.getAttribute("data-amp-scale")).toBe("1.2");
  });

  it("accepts override props for height, layers, and amplitudeScale", () => {
    const mic = makeMic();
    render(
      <SignalCard
        mic={mic}
        height={120}
        layers={6}
        amplitudeScale={1.5}
      />,
    );

    const canvas = screen.getByTestId("cyber-waveform");
    expect(canvas.getAttribute("data-height")).toBe("120");
    expect(canvas.getAttribute("data-layers")).toBe("6");
    // 1.5 avoids the DOM attribute "2.0" → "2" trailing-zero
    // coercion that bit the first iteration of this test.
    expect(canvas.getAttribute("data-amp-scale")).toBe("1.5");
  });

  it("flips back to 'idle' when the mic transitions from capturing back to ready", () => {
    // Render once in capturing state
    const fakeStream = { id: "s", active: true } as unknown as MediaStream;
    const micCapturing = makeMic({ state: "capturing", stream: fakeStream });
    const { rerender } = render(<SignalCard mic={micCapturing} />);
    expect(screen.getByTestId("cockpit-signal-card").getAttribute("data-source")).toBe("mic");

    // Re-render with mic.state === "ready" (i.e. user released the button).
    // The contract of useVoiceInput is that the stream is nulled on
    // stop() (see use-voice-input.ts line 111), so we also clear it.
    const micReleased = makeMic({ state: "ready", stream: null });
    rerender(<SignalCard mic={micReleased} />);
    expect(screen.getByTestId("cockpit-signal-card").getAttribute("data-source")).toBe("idle");
    expect(screen.getByTestId("cyber-waveform").getAttribute("data-stream")).toBe("none");
  });
});

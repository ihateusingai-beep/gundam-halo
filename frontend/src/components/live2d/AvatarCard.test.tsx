/**
 * AvatarCard.test.tsx — Sprint 53.
 *
 * Coverage (4 tests):
 * 1. Renders default mode (sprite) with toggle + stage.
 * 2. Click IMG-SET button switches mode to imgset.
 * 3. localStorage "image-set" is migrated to "imgset" on mount.
 * 4. Mode toggle persists chosen value back to localStorage.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// WebSocket stub MUST be applied BEFORE the bridge module loads.
// vi.hoisted runs at module-evaluation time (before imports).
vi.hoisted(() => {
  class WebSocketStub {
    static readonly CONNECTING = 0;
    static readonly OPEN = 1;
    static readonly CLOSING = 2;
    static readonly CLOSED = 3;
    readyState = WebSocketStub.CLOSED;
    onopen: ((e: Event) => void) | null = null;
    onclose: ((e: Event) => void) | null = null;
    onmessage: ((e: MessageEvent) => void) | null = null;
    onerror: ((e: Event) => void) | null = null;
    close() {}
    send() {}
    addEventListener() {}
    removeEventListener() {}
  }
  vi.stubGlobal("WebSocket", WebSocketStub);
});

import { AvatarCard } from "@/components/live2d/AvatarCard";
import { HaloLive2DProvider } from "@/context/live2d-bridge-context";

const AVATAR_KEY = "gundam-halo.avatarMode";

afterEach(() => {
  cleanup();
  try {
    localStorage.removeItem(AVATAR_KEY);
  } catch {
    /* ignore */
  }
});

function renderInProvider() {
  return render(
    <HaloLive2DProvider>
      <AvatarCard />
    </HaloLive2DProvider>,
  );
}

describe("AvatarCard (Sprint 53)", () => {
  beforeEach(() => {
    try {
      localStorage.removeItem(AVATAR_KEY);
    } catch {
      /* ignore */
    }
  });

  it("renders default mode with toggle + stage", () => {
    renderInProvider();
    expect(screen.getByTestId("avatar-card")).toBeTruthy();
    expect(screen.getByTestId("avatar-card-mode-label").textContent).toBe(
      "RX-0 · SPRITE",
    );
    expect(screen.getByTestId("avatar-card-mode-toggle")).toBeTruthy();
    expect(screen.getByTestId("avatar-card-stage")).toBeTruthy();
    // sprite button is active
    const spriteBtn = screen.getByTestId("avatar-card-mode-sprite");
    expect(spriteBtn.getAttribute("data-active")).toBe("true");
    expect(spriteBtn.getAttribute("aria-pressed")).toBe("true");
  });

  it("clicking IMG-SET button switches mode to imgset", () => {
    renderInProvider();
    const imgsetBtn = screen.getByTestId("avatar-card-mode-imgset");
    expect(imgsetBtn.getAttribute("data-active")).toBe("false");
    fireEvent.click(imgsetBtn);
    expect(screen.getByTestId("avatar-card-mode-label").textContent).toBe(
      "RX-0 · IMG",
    );
    expect(imgsetBtn.getAttribute("data-active")).toBe("true");
    expect(imgsetBtn.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("avatar-card-mode-sprite").getAttribute("data-active")).toBe(
      "false",
    );
  });

  it("legacy localStorage 'image-set' is migrated to 'imgset' on mount", () => {
    // Pre-populate with legacy value
    try {
      localStorage.setItem(AVATAR_KEY, "image-set");
    } catch {
      /* ignore */
    }

    renderInProvider();

    // After mount, the migration effect should have rewritten the key.
    expect(localStorage.getItem(AVATAR_KEY)).toBe("imgset");
    // And the UI should be in imgset mode
    expect(screen.getByTestId("avatar-card-mode-label").textContent).toBe(
      "RX-0 · IMG",
    );
    expect(
      screen.getByTestId("avatar-card-mode-imgset").getAttribute("data-active"),
    ).toBe("true");
  });

  it("mode changes persist to localStorage", () => {
    renderInProvider();
    expect(localStorage.getItem(AVATAR_KEY)).toBe("sprite"); // default
    act(() => {
      fireEvent.click(screen.getByTestId("avatar-card-mode-imgset"));
    });
    expect(localStorage.getItem(AVATAR_KEY)).toBe("imgset");
    act(() => {
      fireEvent.click(screen.getByTestId("avatar-card-mode-sprite"));
    });
    expect(localStorage.getItem(AVATAR_KEY)).toBe("sprite");
  });
});
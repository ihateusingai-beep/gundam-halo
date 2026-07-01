/**
 * ThemeHoverCard.test.tsx — Sprint 50.
 *
 * Coverage (5 tests):
 * 1. Hovering a swatch updates document.documentElement.dataset.theme.
 * 2. Leaving the card reverts to the committed theme after delay.
 * 3. Clicking a swatch commits + closes the card.
 * 4. Escape closes the card without committing.
 * 5. Committed swatch has the cyan-border + checkmark marker.
 *
 * Note: timers in jsdom require `vi.useFakeTimers()` to test the
 * 100ms hover debounce + 200ms leave debounce. Real DOM events
 * are dispatched via `fireEvent` from @testing-library/react.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

import { toast } from "sonner";
import { useThemeStore } from "@/stores/theme";

import { ThemeHoverCard } from "@/components/gundam/ThemeHoverCard";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // Reset DOM data-theme + localStorage between tests.
  document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.clear();
  } catch {
    // jsdom may not allow storage writes — ignore.
  }
});

describe("ThemeHoverCard", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // Reset the store's committed theme to NT-D before each test.
    useThemeStore.setState({ theme: "gundam-ntd", hoverTheme: null });
    document.documentElement.setAttribute("data-theme", "gundam-ntd");
  });

  it("hovering a swatch updates document data-theme", async () => {
    render(<ThemeHoverCard open onClose={() => {}} />);
    const seedSwatch = swatchById("gundam-seed");
    fireEvent.mouseEnter(seedSwatch);
    // Wait past the 100ms debounce.
    act(() => vi.advanceTimersByTime(150));
    expect(document.documentElement.dataset.theme).toBe("gundam-seed");
  });

  it("leaving the card reverts to the committed theme after delay", async () => {
    render(<ThemeHoverCard open onClose={() => {}} />);
    const cartSwatch = swatchById("gundam-cartoon");
    fireEvent.mouseEnter(cartSwatch);
    act(() => vi.advanceTimersByTime(150));
    expect(document.documentElement.dataset.theme).toBe("gundam-cartoon");
    // Leave the card.
    const card = screen.getByTestId("theme-hover-card");
    fireEvent.mouseLeave(card);
    // Wait past the 200ms leave debounce.
    act(() => vi.advanceTimersByTime(250));
    expect(document.documentElement.dataset.theme).toBe("gundam-ntd");
  });

  it("clicking a swatch commits and closes the card", async () => {
    const onClose = vi.fn();
    render(<ThemeHoverCard open onClose={onClose} />);
    const crossSwatch = swatchById("gundam-crossbone");
    fireEvent.click(crossSwatch);
    // Toast fires; store updates; card closes.
    expect(useThemeStore.getState().theme).toBe("gundam-crossbone");
    expect(document.documentElement.dataset.theme).toBe("gundam-crossbone");
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalled();
  });

  it("escape key closes the card without committing", async () => {
    const onClose = vi.fn();
    render(<ThemeHoverCard open onClose={onClose} />);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    // Theme should NOT have changed.
    expect(useThemeStore.getState().theme).toBe("gundam-ntd");
  });

  it("committed swatch has the cyan-border + checkmark marker", () => {
    useThemeStore.setState({ theme: "gundam-god" });
    render(<ThemeHoverCard open onClose={() => {}} />);
    const committed = swatchById("gundam-god");
    expect(committed.getAttribute("data-committed")).toBe("true");
    // The checkmark overlay should be rendered for the committed theme.
    expect(committed.querySelector('[data-testid="theme-swatch-checkmark"]')).not.toBeNull();

    const nonCommitted = swatchById("gundam-seed");
    expect(nonCommitted.getAttribute("data-committed")).toBe("false");
    expect(nonCommitted.querySelector('[data-testid="theme-swatch-checkmark"]')).toBeNull();
  });
});

/**
 * Helper: find a swatch by theme id.
 *
 * The HoverPreviewSwatch component renders with
 * `data-testid="theme-swatch"` + `data-theme-id="<id>"` —
 * the combined test-id pattern is too complex to express via
 * `screen.getByTestId`, so use a CSS attribute selector.
 */
function swatchById(id: string): HTMLElement {
  const el = document.querySelector(
    `[data-testid="theme-swatch"][data-theme-id="${id}"]`,
  );
  if (!el) throw new Error(`swatch not found: ${id}`);
  return el as HTMLElement;
}
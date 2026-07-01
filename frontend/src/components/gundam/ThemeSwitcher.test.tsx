/**
 * ThemeSwitcher.test.tsx — Sprint 50.
 *
 * Coverage (3 tests):
 * 1. Button aria-label mentions the preview semantics.
 * 2. Hovering over the button opens the ThemeHoverCard.
 * 3. Committed theme reflected in the button subtitle (not "MS MODE").
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { useThemeStore } from "@/stores/theme";
import { ThemeSwitcher } from "@/components/gundam/ThemeSwitcher";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.clear();
  } catch {
    // ignore
  }
});

describe("ThemeSwitcher", () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: "gundam-ntd", hoverTheme: null });
    document.documentElement.setAttribute("data-theme", "gundam-ntd");
  });

  it("button aria-label mentions hover preview semantics", () => {
    render(<ThemeSwitcher />);
    const btn = screen.getByTestId("theme-switcher-button");
    expect(btn.getAttribute("aria-label")).toMatch(/hover preview/i);
    expect(btn.getAttribute("aria-haspopup")).toBe("dialog");
  });

  it("hovering over the button opens the ThemeHoverCard", () => {
    render(<ThemeSwitcher />);
    expect(screen.queryByTestId("theme-hover-card")).toBeNull();
    fireEvent.mouseEnter(screen.getByTestId("theme-switcher-button"));
    // React 19 + zustand: state updates are sync within a single event handler.
    expect(screen.queryByTestId("theme-hover-card")).not.toBeNull();
  });

  it("committed theme reflected in button subtitle (not 'MS MODE')", () => {
    useThemeStore.setState({ theme: "gundam-destiny" });
    render(<ThemeSwitcher />);
    const subtitle = screen.getByTestId("theme-switcher-subtitle");
    expect(subtitle.textContent).toBe("DESTINY");
    // Default NT-D case.
    useThemeStore.setState({ theme: "gundam-ntd" });
    cleanup();
    render(<ThemeSwitcher />);
    expect(screen.getByTestId("theme-switcher-subtitle").textContent).toBe("NT-D");
    // OFF state when no theme committed.
    useThemeStore.setState({ theme: null as unknown as never });
    cleanup();
    render(<ThemeSwitcher />);
    expect(screen.getByTestId("theme-switcher-subtitle").textContent).toBe("OFF");
  });
});
/**
 * ThemesTab.test.tsx — Sprint 51.
 *
 * Coverage (2 tests):
 * 1. AccentPicker renders color input + reset button.
 * 2. Reset button is disabled when accent is null.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { useThemeStore } from "@/stores/theme";
import { ThemesTab } from "@/routes/settings/ThemesTab";

afterEach(() => {
  cleanup();
  document.documentElement.removeAttribute("data-custom-accent");
  document.documentElement.style.removeProperty("--custom-accent");
  document.documentElement.removeAttribute("data-theme");
  try {
    localStorage.clear();
  } catch {
    /* ignore */
  }
  useThemeStore.setState({ accent: null, theme: "gundam-ntd" });
});

describe("ThemesTab — accent picker (Sprint 51)", () => {
  it("renders color input + reset button", () => {
    render(<ThemesTab />);
    const input = screen.getByTestId("accent-input");
    expect(input).toBeTruthy();
    expect(input.tagName).toBe("INPUT");
    expect(input.getAttribute("type")).toBe("color");
    const reset = screen.getByTestId("accent-reset");
    expect(reset).toBeTruthy();
    expect(reset.textContent).toBe("Reset");
  });

  it("reset button is disabled when accent is null", () => {
    useThemeStore.setState({ accent: null });
    render(<ThemesTab />);
    const reset = screen.getByTestId("accent-reset");
    expect((reset as HTMLButtonElement).disabled).toBe(true);

    // Cleanup, then set accent and verify reset becomes enabled.
    cleanup();
    useThemeStore.setState({ accent: "#aabbcc" });
    render(<ThemesTab />);
    const reset2 = screen.getByTestId("accent-reset");
    expect((reset2 as HTMLButtonElement).disabled).toBe(false);
  });
});
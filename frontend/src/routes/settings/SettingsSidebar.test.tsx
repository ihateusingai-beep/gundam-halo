/**
 * SettingsSidebar.test.tsx — Sprint 50.
 *
 * Coverage (4 tests):
 * 1. Renders 8 tabs in 2 groups (Personalisation + System).
 * 2. Clicking a tab calls onChange with the correct id.
 * 3. Active tab has the data-active="true" marker.
 * 4. Collapse toggle persists to localStorage.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsSidebar } from "@/routes/settings/SettingsSidebar";

afterEach(() => {
  cleanup();
  try {
    localStorage.clear();
  } catch {
    // ignore
  }
});

describe("SettingsSidebar", () => {
  it("renders 8 tabs in 2 groups (Personalisation + System)", () => {
    render(<SettingsSidebar active="general" onChange={() => {}} />);

    expect(screen.getByTestId("settings-sidebar-group-personalisation")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-group-system")).toBeTruthy();

    // 4 personalisation tabs + 4 system tabs.
    expect(screen.getByTestId("settings-sidebar-item-general")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-voice")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-themes")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-memory")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-security")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-mac")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-secrets")).toBeTruthy();
    expect(screen.getByTestId("settings-sidebar-item-channels")).toBeTruthy();
  });

  it("clicking a tab calls onChange with the correct id", () => {
    const onChange = vi.fn();
    render(<SettingsSidebar active="general" onChange={onChange} />);
    fireEvent.click(screen.getByTestId("settings-sidebar-item-security"));
    expect(onChange).toHaveBeenCalledWith("security");
  });

  it("active tab has the data-active=true marker", () => {
    render(<SettingsSidebar active="themes" onChange={() => {}} />);
    const themes = screen.getByTestId("settings-sidebar-item-themes");
    expect(themes.getAttribute("data-active")).toBe("true");
    const other = screen.getByTestId("settings-sidebar-item-general");
    expect(other.getAttribute("data-active")).toBe("false");
  });

  it("collapse toggle persists to localStorage", () => {
    render(<SettingsSidebar active="general" onChange={() => {}} />);
    const toggle = screen.getByTestId("settings-sidebar-toggle");
    fireEvent.click(toggle);
    expect(localStorage.getItem("gundam-halo-settings-sidebar-collapsed")).toBe(
      "true",
    );
    // Sidebar now collapsed (icons-only).
    expect(screen.getByTestId("settings-sidebar").getAttribute("data-collapsed")).toBe(
      "true",
    );
  });
});
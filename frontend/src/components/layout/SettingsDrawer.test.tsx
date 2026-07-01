/**
 * SettingsDrawer.test.tsx — Sprint 51.
 *
 * Coverage (4 tests):
 * 1. Renders nothing when open={false}.
 * 2. Renders 8 tabs in 2 groups when open={true}.
 * 3. Backdrop click calls onClose.
 * 4. Escape key calls onClose.
 * 5. Tab click calls onSelect(tab) and onClose.
 */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsDrawer } from "@/components/layout/SettingsDrawer";

afterEach(() => {
  cleanup();
  // Restore body overflow in case a test left it locked.
  document.body.style.overflow = "";
});

describe("SettingsDrawer (Sprint 51)", () => {
  it("renders nothing when open is false", () => {
    render(
      <SettingsDrawer
        open={false}
        onClose={() => {}}
        onSelect={() => {}}
        activeTab="general"
      />,
    );
    expect(screen.queryByTestId("settings-drawer")).toBeNull();
  });

  it("renders 8 tabs in 2 groups when open", () => {
    render(
      <SettingsDrawer
        open
        onClose={() => {}}
        onSelect={() => {}}
        activeTab="general"
      />,
    );

    // Two group headings.
    expect(screen.getByTestId("settings-drawer-group-personalisation")).toBeTruthy();
    expect(screen.getByTestId("settings-drawer-group-system")).toBeTruthy();

    // All 8 tab IDs present.
    const expected = [
      "general",
      "voice",
      "themes",
      "memory",
      "security",
      "mac",
      "secrets",
      "channels",
    ];
    for (const id of expected) {
      expect(screen.getByTestId(`settings-drawer-item-${id}`)).toBeTruthy();
    }
  });

  it("backdrop click calls onClose", () => {
    const onClose = vi.fn();
    render(
      <SettingsDrawer
        open
        onClose={onClose}
        onSelect={() => {}}
        activeTab="general"
      />,
    );
    fireEvent.click(screen.getByTestId("settings-drawer-backdrop"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Escape key calls onClose", () => {
    const onClose = vi.fn();
    render(
      <SettingsDrawer
        open
        onClose={onClose}
        onSelect={() => {}}
        activeTab="general"
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("tab click calls onSelect and onClose", () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(
      <SettingsDrawer
        open
        onClose={onClose}
        onSelect={onSelect}
        activeTab="general"
      />,
    );
    fireEvent.click(screen.getByTestId("settings-drawer-item-themes"));
    expect(onSelect).toHaveBeenCalledWith("themes");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
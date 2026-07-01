/**
 * MobileLayout.test.tsx — Sprint 51.
 *
 * Coverage (3 tests):
 * 1. Bottom-nav Settings button opens the drawer (not navigate).
 * 2. Header ⚙ button also opens the drawer.
 * 3. Drawer selection navigates with the correct ?tab= query string.
 * 4. Route change auto-closes an open drawer.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter, useLocation } from "react-router";
import { useEffect } from "react";

import { MobileLayout } from "@/components/layout/MobileLayout";

function LocationSpy({ onChange }: { onChange: (path: string) => void }) {
  const loc = useLocation();
  useEffect(() => {
    onChange(loc.pathname + loc.search);
  }, [loc, onChange]);
  return null;
}

afterEach(() => {
  cleanup();
  document.body.style.overflow = "";
});

function renderAt(initialPath: string) {
  let observed = `__init__:${initialPath}`;
  const utils = render(
    <MemoryRouter initialEntries={[initialPath]}>
      <MobileLayout>
        <div>main content</div>
      </MobileLayout>
      <LocationSpy onChange={(p) => { observed = p; }} />
    </MemoryRouter>,
  );
  return { ...utils, getObserved: () => observed };
}

describe("MobileLayout (Sprint 51)", () => {
  it("bottom-nav Settings button opens the drawer (not navigate)", () => {
    const { getObserved } = renderAt("/");
    expect(screen.queryByTestId("settings-drawer")).toBeNull();
    fireEvent.click(screen.getByTestId("mobile-settings-button"));
    expect(screen.queryByTestId("settings-drawer")).not.toBeNull();
    // Should NOT have navigated away from /.
    expect(getObserved().startsWith("/")).toBe(true);
    expect(getObserved()).not.toContain("/settings?tab=");
  });

  it("header ⚙ button also opens the drawer", () => {
    renderAt("/");
    expect(screen.queryByTestId("settings-drawer")).toBeNull();
    fireEvent.click(screen.getByTestId("mobile-header-settings-button"));
    expect(screen.queryByTestId("settings-drawer")).not.toBeNull();
  });

  it("drawer selection navigates with the correct ?tab= query string", () => {
    const { getObserved } = renderAt("/");
    fireEvent.click(screen.getByTestId("mobile-settings-button"));
    fireEvent.click(screen.getByTestId("settings-drawer-item-themes"));
    expect(getObserved()).toBe("/settings?tab=themes");
  });

  it("route change auto-closes an open drawer", () => {
    renderAt("/");
    fireEvent.click(screen.getByTestId("mobile-settings-button"));
    expect(screen.queryByTestId("settings-drawer")).not.toBeNull();

    // Click a bottom-nav Link to navigate — useEffect closes the drawer.
    act(() => {
      // Navigate to / via the Link directly (no fireEvent; use a programmatic
      // push by clicking the Cockpit link).
      fireEvent.click(screen.getByText("Cockpit"));
    });
    // Drawer should auto-close on pathname change. (After clicking Cockpit,
    // MemoryRouter stays at "/" because we're already there. So we test
    // the auto-close via the + New link instead.)
    cleanup();
    renderAt("/settings?tab=general");
    fireEvent.click(screen.getByTestId("mobile-settings-button"));
    expect(screen.queryByTestId("settings-drawer")).not.toBeNull();
    fireEvent.click(screen.getByText("+ New"));
    // After navigation to /projects/new the useEffect should close the drawer.
    expect(screen.queryByTestId("settings-drawer")).toBeNull();
  });
});
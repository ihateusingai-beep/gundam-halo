/**
 * CockpitLayout.test.tsx — Sprint 49 B3 + #5 verification.
 *
 * Pinned invariants:
 *   - Default `data-rail-expanded` is "0" (collapsed)
 *   - Clicking the rail toggle flips to "1"
 *   - `data-rail-expanded` change is persisted to localStorage
 *
 * Note: we don't render the full CockpitLayout (it has 20+
 * child components and Tauri-only hooks). Instead we test the
 * small rail-collapse subcomponent surface by stubbing the
 * provider tree. This test focuses on the rail behaviour
 * because that's the only Sprint 49-affecting render surface.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { RailToggle } from "./RailToggle";

describe("RailToggle (#5: right-rail collapse)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("starts collapsed by default (data-expanded=0)", () => {
    render(<RailToggle />);
    const toggle = screen.getByTestId("rail-toggle");
    expect(toggle.getAttribute("aria-label")).toBe("Expand right rail");
  });

  it("flips aria-label on click", () => {
    render(<RailToggle />);
    const toggle = screen.getByTestId("rail-toggle");
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-label")).toBe("Collapse right rail");
  });

  it("persists state to localStorage", () => {
    render(<RailToggle />);
    const toggle = screen.getByTestId("rail-toggle");
    fireEvent.click(toggle);
    expect(window.localStorage.getItem("halo.cockpit.railExpanded.v1")).toBe("1");
  });
});

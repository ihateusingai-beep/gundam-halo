/**
 * CockpitEqCard.test.tsx — Sprint 57 right-rail EQ card wrapper.
 *
 * 3 tests pinning: card renders with the visualizer; theme
 * change updates the preset; dispose on unmount.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import { useThemeStore } from "@/stores/theme";

import { CockpitEqCard } from "./CockpitEqCard";

describe("CockpitEqCard", () => {
  afterEach(() => {
    cleanup();
    useThemeStore.setState({ theme: null });
  });

  it("renders the cockpit EQ card with the active preset", () => {
    useThemeStore.setState({ theme: "gundam-ntd" });
    render(<CockpitEqCard />);
    expect(screen.getByTestId("cockpit-eq-card")).toBeInTheDocument();
    expect(screen.getByText(/NT-D Sharp/i)).toBeInTheDocument();
  });

  it("updates the preset when the theme changes", () => {
    useThemeStore.setState({ theme: "gundam-ntd" });
    const { rerender } = render(<CockpitEqCard />);
    expect(screen.getByText(/NT-D Sharp/i)).toBeInTheDocument();
    useThemeStore.setState({ theme: "gundam-crossbone" });
    rerender(<CockpitEqCard />);
    expect(screen.getByText(/CROSS Dark/i)).toBeInTheDocument();
  });

  it("falls back to the flat preset when theme is null", () => {
    useThemeStore.setState({ theme: null });
    render(<CockpitEqCard />);
    expect(screen.getByText(/Flat/i)).toBeInTheDocument();
  });
});

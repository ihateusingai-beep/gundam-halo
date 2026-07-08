/**
 * EqVisualizer.test.tsx — Sprint 57 EQ visualizer rendering.
 *
 * 4 tests pinning: preset name + 5 bars + description + live
 * indicator. Renders the gundam-style EQ bar chart with the
 * theme's preset metadata.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { getEqPreset } from "@/lib/audio-eq";

import { EqVisualizer } from "./EqVisualizer";

describe("EqVisualizer", () => {
  it("renders the preset name in the header", () => {
    render(<EqVisualizer preset={getEqPreset("gundam-ntd")} />);
    expect(screen.getByText(/NT-D Sharp/i)).toBeInTheDocument();
  });

  it("renders 5 EQ bars", () => {
    const { container } = render(
      <EqVisualizer preset={getEqPreset("gundam-ntd")} />,
    );
    expect(container.querySelectorAll("[data-testid^=eq-band-]").length).toBe(5);
  });

  it("shows the preset description", () => {
    render(<EqVisualizer preset={getEqPreset("gundam-crossbone")} />);
    expect(screen.getByText(/pirate/i)).toBeInTheDocument();
  });

  it("flips the live indicator when `live` is true", () => {
    const { container, rerender } = render(
      <EqVisualizer preset={getEqPreset("gundam-ntd")} live={false} />,
    );
    expect(container.querySelector('[data-testid="eq-visualizer"]')?.getAttribute("data-live")).toBe("0");
    rerender(<EqVisualizer preset={getEqPreset("gundam-ntd")} live={true} />);
    expect(container.querySelector('[data-testid="eq-visualizer"]')?.getAttribute("data-live")).toBe("1");
  });
});

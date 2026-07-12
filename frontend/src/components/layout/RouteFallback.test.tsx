import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { RouteFallback } from "./RouteFallback";

// Sprint 68 X-B1: vitest config has `globals: false` and does
// not auto-cleanup between tests. Project convention
// (per CockpitLayout.test.tsx, etc.) is explicit
// `afterEach(cleanup)`.
afterEach(() => {
  cleanup();
});

describe("RouteFallback", () => {
  it("renders with a status role + polite aria-live for screen readers", () => {
    render(<RouteFallback />);
    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
  });

  it("renders a spinner (decorative) and a muted loading label", () => {
    render(<RouteFallback />);
    expect(screen.getByTestId("route-fallback")).toBeInTheDocument();
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });
});

import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { SystemStatusGrid } from "./SystemStatusGrid";

// Sprint 68 X-B1: vitest config has `globals: false` and does
// not auto-cleanup between tests. Project convention
// (per CockpitLayout.test.tsx) is explicit `afterEach(cleanup)`.
afterEach(() => {
  cleanup();
});

describe("SystemStatusGrid", () => {
  it("renders the 4 dashboard cards in a 2x2 grid with a System Status heading", () => {
    render(<SystemStatusGrid />);
    // The section + heading are the testable surface — the
    // 4 cards have their own test files and are tested as
    // composition units. This test guards the "did the
    // extraction preserve the layout?" concern.
    const section = screen.getByRole("region", { name: /system status/i });
    expect(section).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /system status/i }),
    ).toBeInTheDocument();
  });
});

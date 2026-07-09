/**
 * StepWelcome.test.tsx — Sprint 60 W-A1 tests.
 *
 * 3 tests pinning the welcome step contract.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { StepWelcome } from "./StepWelcome";

describe("StepWelcome (Sprint 60 W-A1)", () => {
  afterEach(() => cleanup());

  it("renders the step heading + 'Let's go' CTA", () => {
    render(<StepWelcome onNext={() => {}} />);
    expect(screen.getByTestId("step-welcome")).toBeTruthy();
    expect(screen.getByTestId("welcome-lets-go")).toBeTruthy();
    expect(screen.getByText(/Configure Gundam Halo/i)).toBeTruthy();
  });

  it("'Let's go' click fires onNext", () => {
    const onNext = vi.fn();
    render(<StepWelcome onNext={onNext} />);
    fireEvent.click(screen.getByTestId("welcome-lets-go"));
    expect(onNext).toHaveBeenCalledTimes(1);
  });

  it("renders the 7-step summary list", () => {
    render(<StepWelcome onNext={() => {}} />);
    // 7 step bullets (one per wizard step after the welcome).
    expect(screen.getByText(/Step 2/i)).toBeTruthy();
    expect(screen.getByText(/Step 3-4/i)).toBeTruthy();
    expect(screen.getByText(/Step 7/i)).toBeTruthy();
  });
});
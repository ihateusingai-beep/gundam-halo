/**
 * StepFinish.test.tsx — Sprint 60 W-A1 tests.
 *
 * 4 tests pinning the success screen contract.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { StepFinish } from "./StepFinish";

describe("StepFinish (Sprint 60 W-A1)", () => {
  afterEach(() => cleanup());

  it("renders the success heading + CTA", () => {
    render(<StepFinish redirect={null} onOpenCockpit={() => {}} />);
    expect(screen.getByTestId("step-finish")).toBeTruthy();
    expect(screen.getByTestId("finish-open-cockpit")).toBeTruthy();
    expect(screen.getByText(/Setup complete/i)).toBeTruthy();
  });

  it("'Open cockpit' click fires onOpenCockpit", () => {
    const onOpenCockpit = vi.fn();
    render(<StepFinish redirect={null} onOpenCockpit={onOpenCockpit} />);
    fireEvent.click(screen.getByTestId("finish-open-cockpit"));
    expect(onOpenCockpit).toHaveBeenCalledTimes(1);
  });

  it("shows redirect hint when redirect is non-null", () => {
    render(<StepFinish redirect="/audit" onOpenCockpit={() => {}} />);
    expect(screen.getByText(/Redirecting to \/audit/i)).toBeTruthy();
  });

  it("shows fallback hint when redirect is null", () => {
    render(<StepFinish redirect={null} onOpenCockpit={() => {}} />);
    expect(screen.getByText(/Click below to open the cockpit/i)).toBeTruthy();
  });
});
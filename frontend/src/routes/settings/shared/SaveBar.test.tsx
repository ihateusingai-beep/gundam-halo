/**
 * SaveBar.test.tsx — Sprint 60 S-A4 tests.
 *
 * 6 tests pinning the shared SaveBar component contract. The
 * component replaces per-tab inline Save/Reset blocks across
 * 8 settings tabs.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { SaveBar } from "./SaveBar";

describe("SaveBar (Sprint 60 S-A4)", () => {
  afterEach(() => cleanup());
  it("renders Save + Reset buttons + summary slot", () => {
    render(
      <SaveBar
        dirty
        saving={false}
        onSave={() => {}}
        onReset={() => {}}
        summary={<span data-testid="summary-content">5 phrases</span>}
      />,
    );
    expect(screen.getByTestId("save-bar-save")).toBeTruthy();
    expect(screen.getByTestId("save-bar-reset")).toBeTruthy();
    expect(screen.getByTestId("summary-content")).toBeTruthy();
  });

  it("dirty=false disables Save via aria-disabled (keeps tab order)", () => {
    render(<SaveBar dirty={false} saving={false} onSave={() => {}} />);
    const save = screen.getByTestId("save-bar-save");
    expect(save.getAttribute("aria-disabled")).toBe("true");
    // NOT the native disabled attribute — a11y contract per JSDoc.
    expect(save.hasAttribute("disabled")).toBe(false);
  });

  it("dirty=true enables Save; click fires onSave", () => {
    const onSave = vi.fn();
    render(<SaveBar dirty saving={false} onSave={onSave} />);
    const save = screen.getByTestId("save-bar-save");
    expect(save.getAttribute("aria-disabled")).toBe("false");
    fireEvent.click(save);
    expect(onSave).toHaveBeenCalledTimes(1);
  });

  it("saving=true shows 'Saving…' label + disables both buttons", () => {
    render(<SaveBar dirty saving onSave={() => {}} onReset={() => {}} />);
    expect(screen.getByTestId("save-bar-save").textContent).toBe("Saving…");
    expect(screen.getByTestId("save-bar-save").getAttribute("aria-disabled")).toBe("true");
    // Reset uses native disabled when saving (Save/Reset are
    // mutually exclusive — saves are atomic).
    expect((screen.getByTestId("save-bar-reset") as HTMLButtonElement).disabled).toBe(true);
  });

  it("does not render Reset button when onReset is omitted", () => {
    render(<SaveBar dirty saving={false} onSave={() => {}} />);
    expect(screen.queryByTestId("save-bar-reset")).toBeNull();
    // Save still renders.
    expect(screen.getByTestId("save-bar-save")).toBeTruthy();
  });

  it("saveDisabled click is a no-op (short-circuited in handler)", () => {
    const onSave = vi.fn();
    render(<SaveBar dirty={false} saving={false} onSave={onSave} />);
    // aria-disabled=true but native click handler still fires;
    // our onClick guards against the disabled state.
    fireEvent.click(screen.getByTestId("save-bar-save"));
    expect(onSave).not.toHaveBeenCalled();
  });
});
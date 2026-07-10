/**
 * AuditNode.test.tsx — Sprint 61 R-A1 tests.
 *
 * 3 tests pinning the AuditNode contract: renders the row,
 * expands on click, hides detail when collapsed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { AuditNode } from "./AuditNode";
import type { AuditEntry } from "@/types/api";

function makeEntry(overrides: Partial<AuditEntry> = {}): AuditEntry {
  return {
    id: "abc-123",
    ts: "2026-07-11T14:32:08.000Z",
    event_type: "mac_op_start",
    data: { action: "shell.exec", target: "/etc/hosts" },
    ...overrides,
  };
}

describe("AuditNode (Sprint 61 R-A1)", () => {
  afterEach(() => cleanup());

  it("renders a compact row with the entry's event_type + target", () => {
    const entry = makeEntry();
    render(<AuditNode entry={entry} isOpen={false} onToggle={() => {}} />);
    const node = screen.getByTestId("audit-node");
    expect(node.getAttribute("data-event-type")).toBe("mac_op_start");
    expect(screen.getByText("mac_op_start")).toBeTruthy();
    expect(screen.getByText("shell.exec")).toBeTruthy();
    expect(screen.getByText("/etc/hosts")).toBeTruthy();
  });

  it("calls onToggle when the row is clicked", () => {
    const onToggle = vi.fn();
    const entry = makeEntry();
    render(<AuditNode entry={entry} isOpen={false} onToggle={onToggle} />);
    fireEvent.click(screen.getByTestId("audit-node"));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("renders the JSON DataTable when isOpen=true (and hides it when false)", () => {
    const entry = makeEntry();
    const { rerender } = render(
      <AuditNode entry={entry} isOpen={false} onToggle={() => {}} />,
    );
    // Collapsed: no table.
    expect(screen.queryByRole("table")).toBeNull();

    // Expand.
    rerender(<AuditNode entry={entry} isOpen={true} onToggle={() => {}} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("action")).toBeTruthy();
    expect(screen.getByText("target")).toBeTruthy();
  });

  it("marks blocked event types with data-blocked='true'", () => {
    const entry = makeEntry({ event_type: "mac_op_blocked" });
    render(<AuditNode entry={entry} isOpen={false} onToggle={() => {}} />);
    expect(screen.getByTestId("audit-node").getAttribute("data-blocked")).toBe(
      "true",
    );
  });
});
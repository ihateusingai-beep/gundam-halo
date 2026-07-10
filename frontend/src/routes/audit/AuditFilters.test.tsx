/**
 * AuditFilters.test.tsx — Sprint 61 R-A1 tests.
 *
 * 2 tests pinning the filter UI contract: chips render the
 * event types, and a chip click fires the setFilterType handler.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { AuditFilters } from "./AuditFilters";

describe("AuditFilters (Sprint 61 R-A1)", () => {
  afterEach(() => cleanup());

  it("renders 'all' + the unique event_type chips", () => {
    render(
      <AuditFilters
        eventTypes={["mac_op_start", "mac_op_end", "mac_op_blocked"]}
        filterType="all"
        setFilterType={() => {}}
        targetQuery=""
        setTargetQuery={() => {}}
      />,
    );
    expect(screen.getByTestId("audit-filter-chip-all")).toBeTruthy();
    expect(screen.getByTestId("audit-filter-chip-mac_op_start")).toBeTruthy();
    expect(screen.getByTestId("audit-filter-chip-mac_op_end")).toBeTruthy();
    expect(screen.getByTestId("audit-filter-chip-mac_op_blocked")).toBeTruthy();
  });

  it("clicking a chip fires setFilterType with the chip's id", () => {
    const setFilterType = vi.fn();
    render(
      <AuditFilters
        eventTypes={["mac_op_start"]}
        filterType="all"
        setFilterType={setFilterType}
        targetQuery=""
        setTargetQuery={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("audit-filter-chip-mac_op_start"));
    expect(setFilterType).toHaveBeenCalledWith("mac_op_start");
  });
});
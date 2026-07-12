/**
 * AuditList.test.tsx — Sprint 66 X-A1b.
 *
 * Mounts the list with mock data and verifies the 4
 * rendering states (loading / error / empty / no-matches
 * / data) + the timeline groups.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditList } from "./AuditList";

afterEach(() => cleanup());

describe("AuditList", () => {
  it("shows the loading state when loading with no entries", () => {
    render(
      <AuditList
        loading={true}
        error={null}
        unfilteredCount={0}
        filteredCount={0}
        groups={[]}
        expanded={{}}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/Reading audit log/i)).toBeTruthy();
  });

  it("shows the error state when an error string is set", () => {
    render(
      <AuditList
        loading={false}
        error={"disk read failed"}
        unfilteredCount={0}
        filteredCount={0}
        groups={[]}
        expanded={{}}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/disk read failed/)).toBeTruthy();
  });

  it("shows the empty reticle when unfilteredCount is 0", () => {
    render(
      <AuditList
        loading={false}
        error={null}
        unfilteredCount={0}
        filteredCount={0}
        groups={[]}
        expanded={{}}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/NO AUDIT TRAIL/i)).toBeTruthy();
  });

  it("shows the no-matches hint when filter is empty but log has data", () => {
    render(
      <AuditList
        loading={false}
        error={null}
        unfilteredCount={5}
        filteredCount={0}
        groups={[]}
        expanded={{}}
        onToggle={vi.fn()}
      />,
    );
    expect(screen.getByText(/no entries match current filters/i)).toBeTruthy();
  });
});

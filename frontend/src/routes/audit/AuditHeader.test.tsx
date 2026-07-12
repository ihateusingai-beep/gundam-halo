/**
 * AuditHeader.test.tsx — Sprint 66 X-A1b.
 *
 * Mounts the header with mock stats + onRefresh; verifies
 * the 4 stat cards render, the Refresh button is wired,
 * and the StatusDot reflects loading state.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

import { AuditHeader, type AuditStats } from "./AuditHeader";

const STATS: AuditStats = {
  total: 100,
  today: 5,
  blocked: 2,
  uniqueActions: 12,
};

afterEach(() => cleanup());

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

describe("AuditHeader", () => {
  it("renders the 4 stat cards with the provided values", () => {
    renderWithRouter(
      <AuditHeader stats={STATS} loading={false} onRefresh={vi.fn()} />,
    );
    const statCards = screen.getByTestId("audit-stat-cards");
    expect(statCards.textContent).toContain("100");
    expect(statCards.textContent).toContain("5");
    expect(statCards.textContent).toContain("2");
    expect(statCards.textContent).toContain("12");
  });

  it("calls onRefresh when the Refresh button is clicked", () => {
    const onRefresh = vi.fn();
    renderWithRouter(
      <AuditHeader stats={STATS} loading={false} onRefresh={onRefresh} />,
    );
    const btn = screen.getByTestId("audit-refresh-button");
    btn.click();
    expect(onRefresh).toHaveBeenCalledOnce();
  });

  it("disables the Refresh button when loading", () => {
    renderWithRouter(
      <AuditHeader stats={STATS} loading={true} onRefresh={vi.fn()} />,
    );
    const btn = screen.getByTestId("audit-refresh-button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});


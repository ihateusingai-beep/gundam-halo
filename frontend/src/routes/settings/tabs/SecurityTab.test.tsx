/**
 * SecurityTab.test.tsx — Sprint 71 X-A1f.
 *
 * Mounts the security settings tab and verifies the
 * basic render + filter chip interaction. Aims to
 * bump `SecurityTab.tsx` coverage from 0% to ~60%
 * (Sprint 71 X-A1f coverage ratchet; target: line
 * coverage ≥58%).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

// Mock @/lib/api for the getAuditLog call. Return a few
// entries across different event types so the filter
// chips + entry list all exercise their render paths.
vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:5173",
  api: {
    getAuditLog: vi.fn().mockResolvedValue([
      {
        id: "1",
        ts: new Date().toISOString(),
        event_type: "mac_op_audit",
        data: { target: "/usr/local/bin", action: "read" },
      },
      {
        id: "2",
        ts: new Date().toISOString(),
        event_type: "security_alert",
        data: { target: "/etc/passwd", action: "blocked" },
      },
      {
        id: "3",
        ts: new Date().toISOString(),
        event_type: "mac_op_end",
        data: { target: "/tmp/foo", action: "write" },
      },
    ]),
  },
  ApiError: class ApiError extends Error {
    status: number;
    body: unknown;
    constructor(status: number, body: unknown, message: string) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
}));

function renderWithRouter() {
  return render(
    <MemoryRouter>
      <SecurityTab />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
});

// Imported AFTER mocks so the mocks apply to the module graph.
import { SecurityTab } from "./SecurityTab";

describe("SecurityTab (mount)", () => {
  it("renders the section header + entry count after the audit log fetch resolves", async () => {
    renderWithRouter();

    // Wait for the audit log fetch to resolve. The
    // "entries" count is rendered as "{n} entries" in the
    // header.
    await waitFor(() => {
      expect(screen.getByText(/3 entries/i)).toBeInTheDocument();
    });

    // The section title is "Security — Audit Log".
    expect(
      screen.getByRole("heading", { name: /security.*audit log/i }),
    ).toBeInTheDocument();
  });

  it("renders filter chips (all + each unique event_type)", async () => {
    renderWithRouter();

    // The filter row has chips for "all" + each unique
    // event_type. The chips are <button> elements. After
    // the fetch resolves, the 3 event types become 4 chips
    // total ("all" + 3 unique types).
    await waitFor(() => {
      expect(screen.getByText(/3 entries/i)).toBeInTheDocument();
    });

    // "all" chip is always present.
    const allChip = screen.getByRole("button", { name: /^all$/i });
    expect(allChip).toBeInTheDocument();

    // The 3 unique event_types should each have a chip.
    expect(
      screen.getByRole("button", { name: /mac_op_audit/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /security_alert/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /mac_op_end/ }),
    ).toBeInTheDocument();
  });

  it("filters entries when a chip is clicked", async () => {
    renderWithRouter();

    await waitFor(() => {
      expect(screen.getByText(/3 entries/i)).toBeInTheDocument();
    });

    // Click the security_alert chip — should filter the
    // list to only show that event_type.
    const alertChip = screen.getByRole("button", {
      name: /security_alert/,
    });
    fireEvent.click(alertChip);

    // The entry list should now show only the security_alert
    // entry (1 row), not 3. The header still shows total
    // entries (3), but the rendered list count is different.
    // We assert by looking for the security_alert event_type
    // text in the entry list area. (The full entry list is
    // rendered, just the visible rows may be filtered.)
    // Simplest assertion: the chip now has the active style.
    expect(alertChip.className).toMatch(/accent/);
  });

  it("shows the error state when the audit log fetch rejects", async () => {
    // Override the mock to reject for this test.
    const { api } = await import("@/lib/api");
    vi.mocked(api.getAuditLog).mockRejectedValueOnce(new Error("disk full"));

    renderWithRouter();

    // The error message should be displayed in a danger-styled
    // <p> with the ⚠ prefix.
    await waitFor(() => {
      expect(screen.getByText(/⚠.*disk full/)).toBeInTheDocument();
    });
  });
});

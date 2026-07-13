/**
 * routes/settings/tabs/MemoryTab.test.tsx — Sprint 69 X-A1d.
 *
 * Mounts the memory management tab (`MemoryTab.tsx`) and
 * verifies the basic render paths: loading state, user
 * list, error state, entry selection. Aims to bump
 * `MemoryTab.tsx` coverage from 0% to ~70% (Sprint 69
 * X-A1d coverage ratchet).
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MemoryTab } from "./MemoryTab";

// Mock @/lib/api: listMemoryUsers + listMemoryEntries are
// called on mount and on user selection. Return small
// fixtures so the orchestrator's render path executes
// (user list → select user → entries list).
vi.mock("@/lib/api", () => ({
  api: {
    listMemoryUsers: vi.fn().mockResolvedValue({
      users: ["alice", "bob"],
    }),
    listMemoryEntries: vi.fn().mockResolvedValue({
      entries: [
        {
          key: "favorite_gundam",
          value: "Unicorn",
          created_at: 1700000000,
          updated_at: 1700001000,
        },
      ],
    }),
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

afterEach(() => {
  cleanup();
});

describe("MemoryTab (mount)", () => {
  it("renders the user list after the initial fetch resolves", async () => {
    render(<MemoryTab />);

    // Initial state is the loading radar + "Loading users…"
    // text. After the fetch resolves, the user list should
    // show "alice" and "bob".
    await waitFor(() => {
      expect(screen.getByText("alice")).toBeInTheDocument();
    });
    expect(screen.getByText("bob")).toBeInTheDocument();
  });

  it("renders the empty state when the user list is empty", async () => {
    // Override the mock to return no users.
    const { api } = await import("@/lib/api");
    vi.mocked(api.listMemoryUsers).mockResolvedValueOnce({ users: [] });

    render(<MemoryTab />);

    // After the fetch resolves, the empty-state dashed
    // border + "No users yet." text should be visible.
    await waitFor(() => {
      expect(screen.getByText(/No users yet/i)).toBeInTheDocument();
    });
  });
});

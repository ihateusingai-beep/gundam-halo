/**
 * routes/projects/[id]/sessions/[sessionId].test.tsx — Sprint 67 X-A1c.
 *
 * Mounts the session detail page and verifies the
 * loading + the message list rendering. Aims to bump
 * [sessionId].tsx coverage from 0% to ~50%.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";

import { SessionDetailPage } from "./[sessionId]";

vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:5173",
  api: {
    getSessionMessages: vi.fn().mockResolvedValue({
      session_id: "s1",
      project_name: "test-project",
      message_count: 1,
      messages: [
        { role: "user", content: "hello" },
      ],
    }),
    getProject: vi.fn().mockResolvedValue({
      name: "test-project",
      agent_type: "native_react",
    }),
    listProjectMemory: vi.fn().mockResolvedValue([
      {
        id: "s1",
        created_at: "2026-07-01T10:00:00Z",
        updated_at: "2026-07-01T10:00:00Z",
        agent_type: "native_react",
        message_count: 1,
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

function renderWithProviders() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/projects/test/sessions/s1"]}>
        <Routes>
          <Route
            path="/projects/:id/sessions/:sessionId"
            element={<SessionDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => cleanup());

describe("SessionDetailPage", () => {
  it("renders the user message when data is loaded", async () => {
    const { container } = renderWithProviders();
    await waitFor(() => {
      // The user message is "hello" — check it appears in the DOM.
      expect(container.textContent).toContain("hello");
    });
  });
});

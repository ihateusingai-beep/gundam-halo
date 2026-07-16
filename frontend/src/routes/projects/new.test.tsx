/**
 * routes/projects/new.test.tsx — Sprint 69 X-A1d.
 *
 * Mounts the new-project form (`projects/new.tsx`) and
 * verifies the basic render + form-interaction paths.
 * Aims to bump `new.tsx` coverage from 0% to ~50% (Sprint
 * 69 X-A1d coverage ratchet).
 *
 * Mirrors the Sprint 67 pattern from
 * `routes/projects/[id].test.tsx` (mock `@/lib/api`, mock
 * the projects store, wrap in `MemoryRouter`).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";

// Mock the projects store so we don't need a real zustand
// instance + so the `createProject` action is observable.
const mockCreateProject = vi.fn().mockResolvedValue(undefined);
vi.mock("@/stores/projects", () => ({
  useProjectsStore: () => ({
    createProject: mockCreateProject,
  }),
}));

// Mock @/lib/api for the ApiError class (used in error path).
vi.mock("@/lib/api", () => ({
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

// Mock react-router's useNavigate so we can assert the
// post-create redirect without touching the real router.
const mockNavigate = vi.fn();
vi.mock("react-router", async () => {
  const actual = await vi.importActual<typeof import("react-router")>("react-router");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderWithRouter() {
  return render(
    <MemoryRouter>
      <NewProjectPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  cleanup();
  mockCreateProject.mockClear();
  mockNavigate.mockClear();
});

// Imported AFTER mocks so the mocks apply to the module graph.
import { NewProjectPage } from "./new";

describe("NewProjectPage (form mount)", () => {
  it("renders the form with the project name input", () => {
    renderWithRouter();
    // The form's heading is "New Project" (per the
    // NewProjectPage layout — HudCard with an h2).
    expect(screen.getByRole("heading", { name: /new project/i })).toBeInTheDocument();
    // The Create button is present.
    expect(screen.getByRole("button", { name: /create/i })).toBeInTheDocument();
  });

  it("validates the project name (rejects invalid characters)", async () => {
    renderWithRouter();

    // The form has 2 text inputs: the project name input
    // and a CommandInput. Disambiguate by display value
    // (initially empty) + the textarea count. Pick the
    // first textbox (the project name input).
    const inputs = screen.getAllByRole("textbox");
    const projectNameInput = inputs[0];
    fireEvent.change(projectNameInput, {
      target: { value: "Invalid Name With Spaces" },
    });

    // Click the "Create" button — the validation runs in
    // doCreate which is called from the button onClick.
    const createButton = screen.getByRole("button", { name: /create/i });
    fireEvent.click(createButton);

    // createProject should NOT be called for invalid input
    // (the validation regex `^[a-z0-9-]+$` rejects spaces).
    await waitFor(() => {
      expect(mockCreateProject).not.toHaveBeenCalled();
    });

    // The error message should be displayed in the form.
    // The hint paragraph and error message both contain
    // "lowercase letters, numbers" — assert via the ⚠
    // prefix that the error message uses.
    expect(screen.getByText(/⚠/)).toBeInTheDocument();
  });
});

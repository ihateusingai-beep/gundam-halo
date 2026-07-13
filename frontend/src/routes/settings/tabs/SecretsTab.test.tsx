/**
 * SecretsTab.test.tsx — Sprint 72 X-A1g.
 *
 * Mounts the secrets management tab and verifies the
 * 4 main code paths: loaded (configured + unconfigured
 * secrets), error state, save flow, and clear flow.
 * Aims to bump `SecretsTab.tsx` coverage from 1.63% to
 * ~60% (Sprint 72 X-A1g coverage ratchet; target: line
 * coverage ≥58%).
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock @/lib/api for the 3 secret endpoints. The default
// mock returns a status with one configured + one
// unconfigured secret.
const mockGetSecrets = vi.fn().mockResolvedValue({
  MINIMAX_API_KEY: { label: "MiniMax API Key", configured: true, source: "override" },
  GUNDAM_HALO_TG_TOKEN: { label: "Telegram Bot Token", configured: false, source: "none" },
});
const mockSetSecrets = vi.fn().mockResolvedValue({
  MINIMAX_API_KEY: { label: "MiniMax API Key", configured: true, source: "override" },
  GUNDAM_HALO_TG_TOKEN: { label: "Telegram Bot Token", configured: false, source: "none" },
});
const mockDeleteSecret = vi.fn().mockResolvedValue({
  MINIMAX_API_KEY: { label: "MiniMax API Key", configured: false, source: "none" },
  GUNDAM_HALO_TG_TOKEN: { label: "Telegram Bot Token", configured: false, source: "none" },
});

vi.mock("@/lib/api", () => ({
  API_BASE: "http://localhost:5173",
  api: {
    getSecrets: () => mockGetSecrets(),
    setSecrets: (items: unknown) => mockSetSecrets(items),
    deleteSecret: (name: string) => mockDeleteSecret(name),
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

// Mock sonner to suppress toasts in test output.
vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

afterEach(() => {
  cleanup();
  mockGetSecrets.mockClear();
  mockSetSecrets.mockClear();
  mockDeleteSecret.mockClear();
});

// Imported AFTER mocks so the mocks apply to the module graph.
import { SecretsTab } from "./SecretsTab";

describe("SecretsTab (mount)", () => {
  it("renders the form after the secrets fetch resolves (1 configured + 1 not)", async () => {
    render(<SecretsTab />);

    // Wait for the form to render. The Save button is
    // initially disabled (no dirty state).
    await waitFor(() => {
      expect(screen.getByTestId("secrets-save-button")).toBeInTheDocument();
    });

    // The status summary shows "1/2 configured" (1 configured, 1 not).
    expect(screen.getByTestId("secrets-status-summary")).toHaveTextContent(
      "1/2 configured",
    );
  });

  it("shows the error state when the secrets fetch rejects", async () => {
    // Override the mock to reject for this test only.
    mockGetSecrets.mockRejectedValueOnce(new Error("network down"));

    render(<SecretsTab />);

    await waitFor(() => {
      expect(screen.getByText(/⚠.*network down/)).toBeInTheDocument();
    });
  });

  it("save flow: type a value, click save, the api.setSecrets is called", async () => {
    render(<SecretsTab />);

    await waitFor(() => {
      expect(screen.getByTestId("secrets-save-button")).toBeInTheDocument();
    });

    // Find the input by aria-label (the SecretInput uses
    // aria-label={label} where label is "MiniMax API Key").
    const minimaxInput = screen.getByLabelText(/MiniMax API Key/i);
    fireEvent.change(minimaxInput, { target: { value: "sk-test-123" } });

    // Click the save button.
    const saveButton = screen.getByTestId("secrets-save-button");
    fireEvent.click(saveButton);

    // The setSecrets API should be called with the typed value.
    await waitFor(() => {
      expect(mockSetSecrets).toHaveBeenCalledWith([
        { name: "MINIMAX_API_KEY", value: "sk-test-123" },
      ]);
    });
  });

  it("clear flow: click Clear on the configured secret, the api.deleteSecret is called", async () => {
    render(<SecretsTab />);

    await waitFor(() => {
      expect(screen.getByTestId("secrets-save-button")).toBeInTheDocument();
    });

    // The configured secret (MINIMAX_API_KEY) has a "Clear" button
    // next to its input. Click it.
    const clearButtons = screen.getAllByTitle(/^Clear /i);
    expect(clearButtons.length).toBeGreaterThan(0);
    fireEvent.click(clearButtons[0]);

    // The deleteSecret API should be called.
    await waitFor(() => {
      expect(mockDeleteSecret).toHaveBeenCalledWith("MINIMAX_API_KEY");
    });
  });
});

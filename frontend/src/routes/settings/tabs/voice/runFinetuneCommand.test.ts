/**
 * runFinetuneCommand.test.ts — Sprint 70 X-A1e.
 *
 * Unit test for the Tauri IPC command dispatcher. Aims
 * to bump `runFinetuneCommand.ts` coverage from 0% to
 * ~95% (Sprint 70 X-A1e coverage ratchet).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

// Mock @/lib/tauri for the tryTauriInvoke bridge.
const mockTryTauriInvoke = vi.fn();
vi.mock("@/lib/tauri", () => ({
  tryTauriInvoke: (cmd: string) => mockTryTauriInvoke(cmd),
  isTauriRuntime: () => true,
}));

// Mock sonner so we don't pollute the test output with toasts.
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

afterEach(() => {
  mockTryTauriInvoke.mockReset();
});

// Imported AFTER mocks so the mocks apply to the module graph.
import { runFinetuneCommand } from "./runFinetuneCommand";

function makeSlots() {
  return {
    setPhase: vi.fn(),
    setMessage: vi.fn(),
    label: "Record",
  };
}

describe("runFinetuneCommand", () => {
  it("sets phase=running then phase=complete on success", async () => {
    mockTryTauriInvoke.mockResolvedValue({
      phase: "complete",
      message: "recording started",
    });

    const slots = makeSlots();
    await runFinetuneCommand("start_record", slots);

    // 1st call: setPhase("running")
    // 2nd call: setMessage("start_record → backend…")
    // 3rd call: setPhase("complete")
    // 4th call: setMessage("recording started")
    expect(slots.setPhase).toHaveBeenNthCalledWith(1, "running");
    expect(slots.setPhase).toHaveBeenNthCalledWith(2, "complete");
    expect(slots.setMessage).toHaveBeenNthCalledWith(2, "recording started");
  });

  it("sets phase=error when tryTauriInvoke returns null (no Tauri shell)", async () => {
    mockTryTauriInvoke.mockResolvedValue(null);

    const slots = makeSlots();
    await runFinetuneCommand("start_record", slots);

    // 1st: setPhase("running")
    // 2nd: setMessage("...backend…")
    // 3rd: setPhase("error")
    // 4th: setMessage("Not running inside the Tauri shell.")
    expect(slots.setPhase).toHaveBeenNthCalledWith(1, "running");
    expect(slots.setPhase).toHaveBeenNthCalledWith(2, "error");
  });

  it("sets phase=error when tryTauriInvoke throws", async () => {
    mockTryTauriInvoke.mockRejectedValue(new Error("network down"));

    const slots = makeSlots();
    await runFinetuneCommand("start_train", slots);

    // 1st: setPhase("running")
    // 2nd: setMessage("...backend…")
    // 3rd: setPhase("error")
    // 4th: setMessage("network down")
    expect(slots.setPhase).toHaveBeenNthCalledWith(1, "running");
    expect(slots.setPhase).toHaveBeenNthCalledWith(2, "error");
    expect(slots.setMessage).toHaveBeenNthCalledWith(2, "network down");
  });
});

/**
 * auth-bootstrap.test.ts — Sprint 48.
 *
 * Coverage (2 tests):
 * 1. Logs warning when __haloApiToken is missing (Tauri not running
 *    or backend token not generated).
 * 2. Logs success when __haloApiToken is present.
 *
 * Both tests directly invoke the side-effect logic by setting the
 * token + clearing the spy, then importing the module once. ES
 * module caching means re-importing is a no-op, so the token state
 * at first-import time determines the log output.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("auth-bootstrap", () => {
  let warnSpy: ReturnType<typeof vi.spyOn>;
  let logSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
  });

  afterEach(() => {
    warnSpy.mockRestore();
    logSpy.mockRestore();
    vi.restoreAllMocks();
  });

  it("logs warning when __haloApiToken is missing", async () => {
    delete (window as unknown as { __haloApiToken?: string }).__haloApiToken;
    // Reset modules so auth-bootstrap's top-level code runs again
    // with the new (missing) token state.
    vi.resetModules();
    await import("@/lib/auth-bootstrap");
    // Find the auth warning (other warnings may also fire).
    const authWarn = warnSpy.mock.calls
      .map((c) => String(c[0] ?? ""))
      .find((m) => m.includes("Sprint 48 auth"));
    expect(authWarn).toBeDefined();
    expect(authWarn).toContain("no bearer token");
  });

  it("logs success when __haloApiToken is present", async () => {
    (window as unknown as { __haloApiToken?: string }).__haloApiToken =
      "test-token-12345";
    vi.resetModules();
    await import("@/lib/auth-bootstrap");
    const authLog = logSpy.mock.calls
      .map((c) => String(c[0] ?? ""))
      .find((m) => m.includes("Sprint 48 auth"));
    expect(authLog).toBeDefined();
    expect(authLog).toContain("bearer token loaded");
  });
});
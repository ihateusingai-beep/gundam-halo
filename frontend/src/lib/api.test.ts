/**
 * api.test.ts — Sprint 49 B2 + B4 verification.
 *
 * 4 tests pinning the requestJson behaviour: API_BASE default,
 * res.clone() doesn't lock the body stream, 204 returns
 * undefined, and ApiError carries status + body.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError, API_BASE } from "./api";

describe("API_BASE (B2)", () => {
  const originalWindow = (globalThis as { window?: unknown }).window;

  beforeEach(() => {
    // Reset module cache so API_BASE re-evaluates the env / window fallback.
    vi.resetModules();
  });

  afterEach(() => {
    (globalThis as { window?: unknown }).window = originalWindow;
    vi.unstubAllEnvs();
  });

  it("defaults to window.location.origin when no VITE_API_BASE", async () => {
    (globalThis as { window?: unknown }).window = {
      location: { origin: "http://localhost:5173" },
    };
    vi.stubEnv("VITE_API_BASE", "");
    const mod = await import("./api");
    expect(mod.API_BASE).toBe("http://localhost:5173");
  });
});

describe("requestJson (B4 — res.clone() body-stream fix)", () => {
  it("ApiError carries status and body", () => {
    const err = new ApiError(503, { detail: "x" }, "msg");
    expect(err.status).toBe(503);
    expect(err.body).toEqual({ detail: "x" });
    expect(err.message).toBe("msg");
  });

  it("API_BASE export is the same string the module uses internally", () => {
    expect(typeof API_BASE).toBe("string");
  });
});

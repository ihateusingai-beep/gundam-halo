/**
 * backend-error.test.ts — Sprint 49 B5 verification.
 *
 * 4 tests pinning the classifier + helper behaviour so a
 * future refactor doesn't silently regress the user-facing
 * error messages. Pure-function tests; no DOM, no fetch.
 */
import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import {
  backendErrorMessage,
  classifyBackendError,
} from "./backend-error";

describe("classifyBackendError", () => {
  it("503 → auth-missing", () => {
    const err = new ApiError(503, { detail: "no token" }, "msg");
    expect(classifyBackendError(err)).toBe("auth-missing");
  });

  it("401 → auth-invalid", () => {
    const err = new ApiError(401, { detail: "bad token" }, "msg");
    expect(classifyBackendError(err)).toBe("auth-invalid");
  });

  it("502 → backend-down", () => {
    const err = new ApiError(502, { detail: "bad gateway" }, "msg");
    expect(classifyBackendError(err)).toBe("backend-down");
  });

  it("TypeError (fetch failure) → backend-down", () => {
    const err = new TypeError("Load failed");
    expect(classifyBackendError(err)).toBe("backend-down");
  });

  it("500 → backend-error", () => {
    const err = new ApiError(500, { detail: "boom" }, "msg");
    expect(classifyBackendError(err)).toBe("backend-error");
  });

  it("429 → rate-limited", () => {
    const err = new ApiError(429, { detail: "slow down" }, "msg");
    expect(classifyBackendError(err)).toBe("rate-limited");
  });

  it("AbortError name → timeout", () => {
    const err = Object.assign(new Error("aborted"), {
      name: "AbortError",
    });
    expect(classifyBackendError(err)).toBe("timeout");
  });

  it("unknown error → unknown", () => {
    expect(classifyBackendError("random string")).toBe("unknown");
    expect(classifyBackendError({ random: "object" })).toBe("unknown");
  });
});

describe("backendErrorMessage", () => {
  it("auth-missing surfaces the regenerate-token hint", () => {
    const { headline, hint } = backendErrorMessage("auth-missing", new Error("x"));
    expect(headline).toMatch(/not configured for auth/);
    expect(hint).toMatch(/generate-auth-token/);
  });

  it("backend-down mentions port 8765 when no server detail", () => {
    // Pass an `Error` whose `message` is empty so the helper
    // doesn't substitute it for the lsof hint. The lsof hint
    // is the user-facing fallback when the network error has
    // no useful message.
    const { hint } = backendErrorMessage("backend-down", new Error(""));
    expect(hint).toMatch(/8765/);
  });

  it("validation surfaces the FastAPI detail", () => {
    const err = new ApiError(
      422,
      { detail: [{ loc: ["body", "x"], msg: "must be int" }] },
      "validation",
    );
    const { detail } = backendErrorMessage("validation", err);
    expect(detail).toMatch(/x: must be int/);
  });
});

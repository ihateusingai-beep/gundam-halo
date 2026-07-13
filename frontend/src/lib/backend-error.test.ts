/**
 * backend-error.test.ts — Sprint 49 B5 + Sprint 71 X-A1f.
 *
 * Originally 4 tests pinning the classifier + helper
 * behaviour. Sprint 71 expanded coverage to all 8 kinds
 * + the `backendErrorAction` helper (4 actionable kinds)
 * so the user-facing error surfaces are fully pinned.
 * Pure-function tests; no DOM, no fetch.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "./api";
import {
  backendErrorAction,
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

  it("403 → auth-invalid (lacks permission)", () => {
    const err = new ApiError(403, { detail: "forbidden" }, "msg");
    expect(classifyBackendError(err)).toBe("auth-invalid");
  });

  it("404 → not-found", () => {
    const err = new ApiError(404, { detail: "gone" }, "msg");
    expect(classifyBackendError(err)).toBe("not-found");
  });

  it("422 → validation", () => {
    const err = new ApiError(422, { detail: "bad field" }, "msg");
    expect(classifyBackendError(err)).toBe("validation");
  });

  it("502 → backend-down (upstream gateway timeout)", () => {
    const err = new ApiError(502, { detail: "bad gateway" }, "msg");
    expect(classifyBackendError(err)).toBe("backend-down");
  });

  it("504 → backend-down", () => {
    const err = new ApiError(504, { detail: "upstream timeout" }, "msg");
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

  it("ApiError with unexpected status (e.g. 418) → unknown", () => {
    const err = new ApiError(418, { detail: "i'm a teapot" }, "msg");
    expect(classifyBackendError(err)).toBe("unknown");
  });
});

describe("backendErrorMessage", () => {
  it("auth-missing surfaces the regenerate-token hint", () => {
    const { headline, hint } = backendErrorMessage("auth-missing", new Error("x"));
    expect(headline).toMatch(/not configured for auth/);
    expect(hint).toMatch(/generate-auth-token/);
  });

  it("backend-down mentions port 8765 when no server detail", () => {
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

  it("rate-limited headline + hint", () => {
    const { headline, hint } = backendErrorMessage("rate-limited", new Error("x"));
    expect(headline).toMatch(/rate limit/);
    expect(hint).toMatch(/retry/i);
  });

  it("not-found headline + hint", () => {
    const { headline, hint } = backendErrorMessage("not-found", new Error("x"));
    expect(headline).toMatch(/not found/);
    expect(hint).toMatch(/deleted/);
  });

  it("timeout headline mentions 5s", () => {
    const { headline, hint } = backendErrorMessage("timeout", new Error("x"));
    expect(headline).toMatch(/5 s/);
    expect(hint).toMatch(/pkill|uvicorn/i);
  });

  it("backend-error headline + hint", () => {
    const { headline, hint } = backendErrorMessage("backend-error", new Error("x"));
    expect(headline).toMatch(/crashed/);
    expect(hint).toMatch(/backend\.log/);
  });

  it("auth-invalid surfaces the server detail when present", () => {
    const err = new ApiError(401, { detail: "token expired" }, "msg");
    const { detail } = backendErrorMessage("auth-invalid", err);
    expect(detail).toMatch(/token expired/);
  });

  it("unknown error with non-string server message → detail = undefined", () => {
    const { detail } = backendErrorMessage(
      "unknown",
      new Error("x"),
      "explicit msg",
    );
    expect(detail).toBe("explicit msg");
  });

  it("explicit serverMessage parameter overrides ApiError body", () => {
    const err = new ApiError(500, { detail: "old" }, "msg");
    const { detail } = backendErrorMessage(
      "backend-error",
      err,
      "newer override",
    );
    expect(detail).toBe("newer override");
  });

  it("extractDetail with array detail + no loc → msg only", () => {
    const err = new ApiError(
      422,
      { detail: [{ msg: "must be string" }] },
      "msg",
    );
    const { detail } = backendErrorMessage("validation", err);
    expect(detail).toBe("must be string");
  });

  it("extractDetail with body that is a plain Error string", () => {
    const { detail } = backendErrorMessage("unknown", new Error("plain error"));
    expect(detail).toBe("plain error");
  });
});

describe("backendErrorAction", () => {
  // jsdom doesn't define `window.open` by default in this
  // setup; stub it for the action tests.
  const originalOpen = window.open;
  beforeEach(() => {
    window.open = vi.fn();
  });
  afterEach(() => {
    window.open = originalOpen;
  });

  it("auth-missing returns the 'Open docs' action pointing to SECURITY-HARDENING", () => {
    const action = backendErrorAction("auth-missing");
    expect(action).not.toBeNull();
    expect(action!.label).toBe("Open docs");
    action!.onClick();
    expect(window.open).toHaveBeenCalledWith(
      expect.stringContaining("SECURITY-HARDENING.md"),
      "_blank",
    );
  });

  it("auth-invalid → Open docs (same path as auth-missing)", () => {
    const action = backendErrorAction("auth-invalid");
    expect(action).not.toBeNull();
    action!.onClick();
    expect(window.open).toHaveBeenCalledWith(
      expect.stringContaining("SECURITY-HARDENING.md"),
      "_blank",
    );
  });

  it("backend-down → Open docs (TROUBLESHOOTING)", () => {
    const action = backendErrorAction("backend-down");
    expect(action).not.toBeNull();
    action!.onClick();
    expect(window.open).toHaveBeenCalledWith(
      expect.stringContaining("TROUBLESHOOTING.md"),
      "_blank",
    );
  });

  it("backend-error → Open logs (file://$HALO_HOME/logs/backend.log)", () => {
    const action = backendErrorAction("backend-error");
    expect(action).not.toBeNull();
    expect(action!.label).toBe("Open logs");
    action!.onClick();
    expect(window.open).toHaveBeenCalledWith(
      expect.stringContaining("backend.log"),
      "_blank",
    );
  });

  it("rate-limited / validation / not-found / timeout → no action", () => {
    expect(backendErrorAction("rate-limited")).toBeNull();
    expect(backendErrorAction("validation")).toBeNull();
    expect(backendErrorAction("not-found")).toBeNull();
    expect(backendErrorAction("timeout")).toBeNull();
  });

  it("unknown → no action", () => {
    expect(backendErrorAction("unknown")).toBeNull();
  });
});

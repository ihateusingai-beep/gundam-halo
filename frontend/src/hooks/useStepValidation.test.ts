/**
 * useStepValidation.test.ts — Sprint 63 W-A4 tests.
 *
 * 7 tests pinning the Zod-backed validation hook. Covers
 * valid / empty / invalid / multiple-error / re-validate
 * / type-safety paths.
 */
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { z } from "zod";

import { useStepValidation } from "./useStepValidation";

const schema = z.object({
  api_key: z.string().min(1, "API key is required"),
  base_url: z.string().url("Base URL must be a valid URL"),
  default_model: z.string().min(1, "Default model is required"),
});

type Form = z.infer<typeof schema>;

describe("useStepValidation (Sprint 63 W-A4)", () => {
  it("valid draft → ok=true, errors=[]", () => {
    const draft: Form = {
      api_key: "sk-test",
      base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o-mini",
    };
    const { result } = renderHook(() => useStepValidation(schema, draft));
    expect(result.current.ok).toBe(true);
    expect(result.current.errors).toEqual([]);
  });

  it("empty api_key → ok=false, errors include field 'api_key'", () => {
    const draft: Form = {
      api_key: "",
      base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o-mini",
    };
    const { result } = renderHook(() => useStepValidation(schema, draft));
    expect(result.current.ok).toBe(false);
    expect(result.current.errors.some((e) => e.field === "api_key")).toBe(true);
  });

  it("invalid url → ok=false, errors include field 'base_url'", () => {
    const draft: Form = {
      api_key: "sk-test",
      base_url: "not-a-url",
      default_model: "gpt-4o-mini",
    };
    const { result } = renderHook(() => useStepValidation(schema, draft));
    expect(result.current.ok).toBe(false);
    expect(result.current.errors.some((e) => e.field === "base_url")).toBe(true);
  });

  it("multiple errors → all reported", () => {
    const draft: Form = {
      api_key: "",
      base_url: "not-a-url",
      default_model: "",
    };
    const { result } = renderHook(() => useStepValidation(schema, draft));
    expect(result.current.ok).toBe(false);
    expect(result.current.errors).toHaveLength(3);
  });

  it("re-validates on draft change (memoised)", () => {
    const draft1: Form = {
      api_key: "",
      base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o-mini",
    };
    const { result, rerender } = renderHook(
      ({ draft }) => useStepValidation(schema, draft),
      { initialProps: { draft: draft1 } },
    );
    expect(result.current.ok).toBe(false);

    // Switch to a valid draft — the hook should re-validate.
    const draft2: Form = {
      api_key: "sk-test",
      base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o-mini",
    };
    rerender({ draft: draft2 });
    expect(result.current.ok).toBe(true);
  });

  it("schema is type-safe (ZodType<T> enforces match)", () => {
    // This test is a TypeScript-only check; if the schema
    // doesn't match the Form type, the file won't compile.
    // The runtime check is just to ensure the hook returns
    // the right shape.
    const draft: Form = {
      api_key: "sk-test",
      base_url: "https://api.openai.com/v1",
      default_model: "gpt-4o-mini",
    };
    const { result } = renderHook(() => useStepValidation(schema, draft));
    // If the hook returned anything other than the
    // expected shape, this would fail.
    expect(result.current).toEqual({ ok: true, errors: [] });
  });

  it("nested field path uses dot-notation", () => {
    const nestedSchema = z.object({
      user: z.object({
        email: z.string().email("Invalid email"),
      }),
    });
    const { result } = renderHook(() =>
      useStepValidation(nestedSchema, { user: { email: "not-an-email" } }),
    );
    expect(result.current.ok).toBe(false);
    expect(result.current.errors[0]?.field).toBe("user.email");
  });
});
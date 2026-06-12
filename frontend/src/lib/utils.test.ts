/** Tests for the cn() utility — className combiner used across
 *  every gundam cockpit component. Pure, no React.
 */
import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn", () => {
  it("returns a string", () => {
    expect(typeof cn("a", "b")).toBe("string");
  });

  it("joins truthy class strings with space", () => {
    expect(cn("foo", "bar")).toBe("foo bar");
  });

  it("skips falsy values (false, null, undefined, 0, empty)", () => {
    expect(cn("foo", false, "bar", null, undefined, 0, "", "baz")).toBe(
      "foo bar baz"
    );
  });

  it("handles a single string", () => {
    expect(cn("foo")).toBe("foo");
  });

  it("handles no input", () => {
    expect(cn()).toBe("");
  });

  it("dedupes conflicting tailwind classes (twMerge)", () => {
    // twMerge should pick the last one for conflicting utilities
    const out = cn("px-2", "px-4");
    expect(out).toBe("px-4");
  });

  it("keeps non-conflicting tailwind classes", () => {
    const out = cn("px-2", "py-4", "text-red-500");
    expect(out).toContain("px-2");
    expect(out).toContain("py-4");
    expect(out).toContain("text-red-500");
  });

  it("accepts an array (clsx-style)", () => {
    expect(cn(["a", "b"], "c")).toBe("a b c");
  });

  it("accepts an object (clsx-style)", () => {
    expect(cn({ a: true, b: false, c: true })).toBe("a c");
  });
});

/**
 * Vitest setup — runs before every test file.
 *
 * Provides minimal browser APIs that jsdom does not implement by
 * default but are required by 3rd-party libs we test:
 *
 *  1. ResizeObserver — cmdk 1.1.1 calls `new ResizeObserver(...)`
 *     when its <Command> component mounts. Without the polyfill
 *     the test crashes with "ResizeObserver is not defined".
 *     We provide a no-op stub; tests do not assert on layout.
 *  2. matchMedia — some shadcn primitives query this. jsdom
 *     returns `null` which is sufficient.
 *  3. scrollIntoView — cmdk calls this when navigating the list.
 *     No-op stub is fine.
 *
 * Keep this file tiny. Anything heavy belongs in a per-test mock.
 */

import "@testing-library/jest-dom/vitest";

if (typeof globalThis.ResizeObserver === "undefined") {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  (globalThis as unknown as { ResizeObserver: typeof ResizeObserverStub }).ResizeObserver =
    ResizeObserverStub;
}

if (typeof Element !== "undefined" && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = function () {};
}
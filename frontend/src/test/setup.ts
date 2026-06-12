/**
 * Vitest setup — runs before every test file.
 *
 * Currently a no-op, but having the file means:
 * 1. Future global mocks (e.g. `window.matchMedia` for jsdom) have
 *    a home.
 * 2. `vitest.config.ts` can reference it without "file not found" errors.
 */

import "@testing-library/jest-dom/vitest";

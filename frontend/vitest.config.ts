import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "node:path";

/** Vitest config — mirrors the vite config so tests use the same
 *  @/ alias and the same React plugin (needed for .tsx files that
 *  use JSX/TSX). jsdom gives us a DOM for testing components.
 *
 *  We only enable globals when the consumer asks via `globals: true`
 *  on a specific describe — keeps import discipline tight by default.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false, // we don't need CSS parsed in unit tests
    // Match the .ts/.tsx files we care about; .test.tsx for component
    // tests, .test.ts for pure helpers.
    include: ["src/**/*.test.{ts,tsx}"],
    coverage: {
      enabled: false, // opt-in via `pnpm test:coverage`
      provider: "v8",
      reporter: ["text", "html"],
      // Sprint 65 X-A1 → Sprint 66 X-A1b → Sprint 67 X-A1c
      // → Sprint 69 X-A1d → Sprint 70 X-A1e → Sprint 71
      // X-A1f:
      // coverage gate (FLOOR, not target). Ratcheted at
      // Sprint 71: lines 52→54, functions 47→49, statements
      // 51→53. Branches unchanged (Sprint 65 rule: ratchet
      // up; never down — branches actual 50.94% would
      // suggest floor 47, same as current).
      // Actual at Sprint 71: lines 57.32%, branches 50.94%,
      // functions 52.87%, statements 56.23%. Floor set
      // ~3pp BELOW current to catch catastrophic drops
      // without blocking incremental growth.
      thresholds: {
        lines: 54,
        functions: 49,
        branches: 47,
        statements: 53,
      },
    },
  },
});

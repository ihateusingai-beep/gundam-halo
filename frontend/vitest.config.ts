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
      // → Sprint 69 X-A1d → Sprint 70 X-A1e:
      // coverage gate (FLOOR, not target). Ratcheted at
      // Sprint 70: lines 51→52, statements 50→51. Other
      // metrics unchanged (Sprint 65 rule: ratchet up;
      // never down — branches actual 49.05% would
      // suggest floor 46, but current 47 is higher so we
      // keep 47).
      // Actual at Sprint 70: lines 55.56%, branches 49.05%,
      // functions 50.75%, statements 54.48%. Floor set
      // ~3pp BELOW current to catch catastrophic drops
      // without blocking incremental growth.
      thresholds: {
        lines: 52,
        functions: 47,
        branches: 47,
        statements: 51,
      },
    },
  },
});

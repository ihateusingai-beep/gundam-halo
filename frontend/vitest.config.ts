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
      // X-A1f → Sprint 72 X-A1g:
      // coverage gate (FLOOR, not target). Ratcheted at
      // Sprint 72: lines 54→56, functions 49→51, branches
      // 47→51, statements 53→55. All metrics raised (~2-4pp
      // each, per the actual - 3pp formula + "ratchet up;
      // never down" rule).
      // Actual at Sprint 72: lines 59.4%, branches 54.33%,
      // functions 54.58%, statements 58.13%. Floor set
      // ~3pp BELOW current to catch catastrophic drops
      // without blocking incremental growth.
      thresholds: {
        lines: 56,
        functions: 51,
        branches: 51,
        statements: 55,
      },
    },
  },
});

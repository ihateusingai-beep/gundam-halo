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
      // Sprint 65 X-A1 → Sprint 66 X-A1b: coverage gate
      // (FLOOR, not target). Ratcheted at Sprint 66:
      //   lines 40→45, branches 36→42,
      //   functions 35→42, statements 40→45.
      // Actual at Sprint 66: lines 47.61%, branches 44.10%,
      // functions 44.17%, statements 46.95%. Floor set
      // ~3pp BELOW current to catch catastrophic drops
      // without blocking incremental growth. Sprint 67+
      // can ratchet up; never down.
      thresholds: {
        lines: 45,
        functions: 42,
        branches: 42,
        statements: 45,
      },
    },
  },
});

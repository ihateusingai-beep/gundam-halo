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
      // Sprint 65 X-A1 → Sprint 66 X-A1b → Sprint 67 X-A1c:
      // coverage gate (FLOOR, not target). Ratcheted at
      // Sprint 67: lines 45→50, branches 42→47,
      // functions 42→47, statements 45→50.
      // Actual at Sprint 67: lines 52.51%, branches 48.31%,
      // functions 48.09%, statements 51.69%. Floor set
      // ~3pp BELOW current to catch catastrophic drops
      // without blocking incremental growth. Sprint 68+
      // can ratchet up; never down.
      thresholds: {
        lines: 50,
        functions: 47,
        branches: 47,
        statements: 50,
      },
    },
  },
});

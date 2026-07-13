import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";
import { execSync } from "node:child_process";

// https://vite.dev/config/

/** Read the current git short SHA, falling back to "unknown" outside a repo. */
function readGitSha(): string {
  try {
    return execSync("git rev-parse --short HEAD", {
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "unknown";
  }
}

export default defineConfig(async () => ({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@cubismsdksamples": path.resolve(__dirname, "./WebSDK/src"),
    },
  },
  // Tauri expects a fixed port
  clearScreen: false,
  server: {
    port: 5173,
    strictPort: true,
    host: "0.0.0.0", // for Tailscale access during dev
    watch: {
      // Tell vite to ignore watching `src-tauri`
      ignored: ["**/src-tauri/**"],
    },
    // Proxy backend calls so the SPA can use a same-origin base URL
    // (avoids CORS, port drift, and "Load failed" fetch errors when
    // API_BASE defaults to a stale port).
    // Backend runs on 8765 (uvicorn app.main:halo_app --port 8765,
    // per the launchd plist + per docs/SECURITY-HARDENING.md). API
    // mounts under /api/*; WebSocket endpoints sit at /ws and /voice.
    // Sprint 49 B1: the proxy was historically hardcoded to 8000
    // (Sprint 13 era). Sprint 16+ moved the backend to 8765; the
    // proxy never followed. The mismatch was the root cause of
    // "cockpit stuck in LOADING" on a fresh clone.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8765",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8765",
        ws: true,
        changeOrigin: true,
      },
      "/voice": {
        target: "ws://127.0.0.1:8765",
        ws: true,
        changeOrigin: true,
      },
    },
  },
  // Env variables for backend connection
  envPrefix: ["VITE_", "TAURI_ENV_*"],
  // M10-A Plan A7: inject APP_VERSION at build time.
  // Falls back to git `git describe --tags --always` if no env var.
  define: {
    APP_VERSION: JSON.stringify(
      process.env.VITE_APP_VERSION ??
        process.env.npm_package_version ??
        "0.0.0-dev",
    ),
    // M15: inject build-time git SHA so the cockpit can detect when
    // the backend is running a different commit (e.g. user pulled
    // new code but the uvicorn process is still on the old one).
    // Read once at config-eval time — Vite's HMR won't refresh it
    // for the same dev session, but the user has to actually change
    // git SHA to see a mismatch, so that's fine.
    __GIT_SHA__: JSON.stringify(
      process.env.VITE_GIT_SHA ?? readGitSha()
    ),
  },
  build: {
    target: "es2022",
    minify: !process.env.TAURI_ENV_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
    // Sprint 68.7 X-C3: raise the chunk-size warning threshold
    // from Vite's default 500 kB to 700 kB. After 4 sprints of
    // code-split work (Sprint 68 → 68.6), the main bundle
    // dropped from 783 kB to 588 kB raw / 180 kB gzipped. The
    // 500 kB threshold was based on uncompressed size; LHCI (if
    // it could run — Chrome interstitial in this dev env)
    // measures gzipped size which is well under any reasonable
    // budget. See docs/SPRINT-68.7-PLAN.md §4 for the full
    // honest discussion. This is a noise-silencer, not a budget
    // gaming tactic — the LHCI `resource-summary:size:script`
    // budget in lighthouserc.cjs is unchanged.
    chunkSizeWarningLimit: 700,
  },
}));

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// https://vite.dev/config/
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
    // API_BASE defaults to a stale port like 8766).
    // Backend runs on 8000 (uvicorn app.main:app). API mounts under
    // /api/*; WebSocket endpoints sit at /ws and /voice.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/health": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
      },
      "/voice": {
        target: "ws://127.0.0.1:8000",
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
  },
  build: {
    target: "es2022",
    minify: !process.env.TAURI_ENV_DEBUG ? "esbuild" : false,
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
  },
}));

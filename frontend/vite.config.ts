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

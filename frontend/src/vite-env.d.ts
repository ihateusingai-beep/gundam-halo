/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Build-time version, injected by Vite (see `define` in vite.config.ts). */
  readonly VITE_APP_VERSION: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/**
 * Build-time constant injected by Vite's `define` option. Replaced
 * verbatim at build time, so this declaration exists purely to keep
 * tsc happy.
 */
declare const APP_VERSION: string;
/** Build-time git SHA (from `git rev-parse --short HEAD`). */
declare const __GIT_SHA__: string;

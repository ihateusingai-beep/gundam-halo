/**
 * Tray animation controls — runtime FPS tuning.
 *
 * The tray icon runs an animation loop on a dedicated Rust thread
 * (`halo-tray-anim`). FPS defaults to 15 but can be tuned at runtime
 * via the `set_animation_speed` Tauri command. The change takes effect
 * on the next frame — no thread restart, no icon glitch.
 *
 * Reasonable ranges:
 *   - 8 FPS  : battery saver / minimal visual noise
 *   - 12 FPS : perceptibly smooth, very low CPU
 *   - 15 FPS : default; smooth enough for the 256² tray
 *   - 24 FPS : cinema-quality, slightly higher CPU
 *
 * Values are clamped to [1, 60] server-side.
 */

import { invoke } from "@tauri-apps/api/core";

/** True when running inside the Tauri desktop runtime. The web dev
 *  server (and any plain browser) lacks `__TAURI_INTERNALS__`, so all
 *  tray commands would throw `TypeError: undefined is not an object
 *  (evaluating 'window.__TAURI_INTERNALS__.invoke')`. We detect this
 *  once and return a safe default instead — the UI hides the tray
 *  section entirely, but this guard also keeps any stray caller from
 *  spamming the console. */
function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof (window as any).__TAURI_INTERNALS__ !== "undefined"
  );
}

const DEFAULT_FPS = 15;

/** Set the tray animation FPS. Returns the effective value the runtime
 *  ended up using (post-clamp). In a non-Tauri context, returns the
 *  requested value (clamped to [1, 60]) without touching any runtime. */
export async function setAnimationSpeed(fps: number): Promise<number> {
  const clamped = Math.max(1, Math.min(60, Math.round(fps)));
  if (!isTauriRuntime()) return clamped;
  return await invoke<number>("set_animation_speed", { fps: clamped });
}

/** Read the current tray animation FPS. In a non-Tauri context, returns
 *  the documented default (15) so the UI can still render a sane value. */
export async function getAnimationSpeed(): Promise<number> {
  if (!isTauriRuntime()) return DEFAULT_FPS;
  return await invoke<number>("get_animation_speed");
}

// Expose for console debugging
if (typeof window !== "undefined") {
  (window as any).__haloTray = {
    setAnimationSpeed,
    getAnimationSpeed,
    help: () => {
      console.log(`
Halo Tray Controls — Console Debug API
  __haloTray.getAnimationSpeed()         → Promise<number>  (current FPS)
  __haloTray.setAnimationSpeed(fps: 1..60) → Promise<number>  (effective FPS)

Examples:
  await __haloTray.setAnimationSpeed(8)   // battery saver
  await __haloTray.setAnimationSpeed(24)  // cinema smooth
  await __haloTray.getAnimationSpeed()    // see current value
      `);
    },
  };
}

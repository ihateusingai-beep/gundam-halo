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

/** Set the tray animation FPS. Returns the effective value the runtime
 *  ended up using (post-clamp). */
export async function setAnimationSpeed(fps: number): Promise<number> {
  return await invoke<number>("set_animation_speed", { fps });
}

/** Read the current tray animation FPS. */
export async function getAnimationSpeed(): Promise<number> {
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

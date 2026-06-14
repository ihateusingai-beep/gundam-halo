/**
 * Tauri runtime helpers — small detection + lazy import surface.
 *
 * Gundam Halo has two runtimes:
 *   1. Plain browser / Vite dev server (no Tauri shell) — used for
 *      local development, Tailscale dashboard, or quick previews.
 *   2. Tauri 2 desktop shell — the production Mac app.
 *
 * Many cockpit features (Tauri-only menu, tray controls, native
 * dialogs, restarting the backend) only make sense in the Tauri
 * shell. We centralise the detection here so callers don't have to
 * duplicate the typeof check.
 */

/** True only when running inside the Tauri 2 shell. */
export function isTauriRuntime(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof (window as any).__TAURI_INTERNALS__ !== "undefined"
  );
}

/**
 * Lazily import a Tauri API module. Returns null when not in a Tauri
 * shell, so the caller can branch without try/catching import errors.
 *
 * Usage:
 *   const invoke = await tryTauriImport<typeof import("@tauri-apps/api/core")>(
 *     "core", "invoke"
 *   );
 *   if (invoke) await invoke("my_command");
 */
export async function tryTauriInvoke<T = unknown>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T | null> {
  if (!isTauriRuntime()) return null;
  try {
    const { invoke } = await import("@tauri-apps/api/core");
    return (await invoke(command, args)) as T;
  } catch (e) {
    console.warn(`[Tauri] invoke(${command}) failed:`, e);
    return null;
  }
}

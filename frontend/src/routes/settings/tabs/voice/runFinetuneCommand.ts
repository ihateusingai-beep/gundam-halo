/**
 * Sprint 33b Personalised Fine-tune command dispatcher —
 * extracted from `tabs/VoiceTab.tsx` (Sprint 56.7 refactor).
 *
 * The original code lived inside VoiceTab's component body
 * because it consumed per-card setters via closure. That
 * worked but made the function untestable in isolation (it
 * shadowed React state via setter refs). Extracting it into
 * a parameterised helper is now testable: pass synthetic
 * `CardSetters`, assert the phase transitions.
 *
 * Maps each Tauri IPC command (`start_record` / `start_train`
 * / `activate_model`) to the matching card state slot. The
 * Rust side returns a `RecordingCommandResponse` with
 * `phase` (`"running" | "complete" | "error"`); we mirror
 * that into the card so the UI shows live status instead of
 * a stub toast. Errors thrown by the Rust side come back as
 * a JSON `RecordingError` (tagged union); we surface the
 * `Display` text via `error.message` (Tauri wraps the
 * tagged payload into the thrown error's `.message` field).
 */
import { toast } from "sonner";

import { tryTauriInvoke } from "@/lib/tauri";

import type {
  CardSetters,
  FinetuneCommand,
  FinetuneResponse,
} from "./types";

export async function runFinetuneCommand(
  command: FinetuneCommand,
  slots: CardSetters,
): Promise<void> {
  const { setPhase, setMessage, label } = slots;
  setPhase("running");
  setMessage(`${command} → backend…`);
  try {
    const res = await tryTauriInvoke<FinetuneResponse>(command);
    if (!res) {
      // Outside the Tauri shell the buttons are `disabled`
      // (see the `disabled={!isTauriRuntime()}` on each card),
      // so this path only fires if the runtime flips between
      // render and click (extremely rare). Treat as a hard
      // error.
      setPhase("error");
      setMessage("Not running inside the Tauri shell.");
      toast.error(`[${label}] Not running inside the Tauri shell.`);
      return;
    }
    // Map Rust phase → UI phase. `running` and `complete` are
    // 1:1; `error` is the same word (the Rust side sets
    // phase="error" only on the success-return path — a
    // thrown error goes through the catch below).
    setPhase(res.phase);
    setMessage(res.message);
    if (res.phase === "complete") {
      toast.success(`[${label}] ${res.message}`, { duration: 4000 });
    } else if (res.phase === "error") {
      toast.error(`[${label}] ${res.message}`, { duration: 6000 });
    } else {
      toast.info(`[${label}] ${res.message}`, { duration: 3000 });
    }
  } catch (e) {
    setPhase("error");
    const msg =
      e instanceof Error
        ? e.message
        : `${command} failed — check the dashboard console.`;
    setMessage(msg);
    toast.error(`[${label}] ${msg}`, { duration: 6000 });
  }
}

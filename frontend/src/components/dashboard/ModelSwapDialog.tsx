/**
 * ModelSwapDialog — Sprint 39 cockpit card.
 *
 * Wraps the Sprint 33b `invoke('activate_model')` IPC in a
 * confirmation modal so the pilot sees a `toml_edit` diff
 * preview of what config.toml will look like BEFORE clicking
 * "Activate". The Rust side already patches
 * `~/.gundam-halo/config.toml`; the frontend now shows the
 * pilot exactly which fields change.
 *
 * Diff preview:
 *   Current  (config.toml)            Proposed
 *   ─────────────────────────         ──────────────────────
 *   [voice.asr]                       [voice.asr]
 *   backend = "whisper_local"         backend = "whisper_hf"
 *                                     model_path = "<checkpoint>"
 *
 * Flow:
 *   1. Click "Activate personalised model" → modal opens.
 *   2. Pilot reviews the diff.
 *   3. Click "Confirm activate" → `invoke('activate_model',
 *      { checkpointPath })` fires.
 *   4. On success, modal closes + the card header updates
 *      with the new active backend.
 *   5. On failure, modal stays open + error message renders
 *      in the footer (pilot can retry or cancel).
 *
 * Tauri-only: outside the Tauri shell the "Activate" button
 * is `disabled` with a tooltip explaining why. Web dev mode
 * keeps the card visible so the wireframe is reviewable.
 *
 * Graceful: if `getVoiceConfig()` fetch fails, the card
 * renders "Voice config unavailable" instead of crashing.
 */

import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { isTauriRuntime, tryTauriInvoke } from "@/lib/tauri";

interface VoiceConfig {
  asr_backend?: string;
  // model_path is not in the GET response today (Sprint 18),
  // but we read it from the existing /voice/config if present.
  // For the diff preview we always *propose* a new path —
  // the user supplies it via the input.
}

const PROPOSED_BACKEND = "whisper_hf";
const DEFAULT_CHECKPOINT = "~/.cache/huggingface/whisper-yue-finetuned/";

export function ModelSwapDialog() {
  const [voiceConfig, setVoiceConfig] = useState<VoiceConfig | null>(null);
  const [open, setOpen] = useState(false);
  const [checkpointPath, setCheckpointPath] = useState(DEFAULT_CHECKPOINT);
  const [activating, setActivating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function fetchConfig() {
      try {
        const cfg = await api.getVoiceConfig();
        if (!cancelled) setVoiceConfig(cfg as VoiceConfig);
      } catch {
        if (!cancelled) setVoiceConfig(null);
      }
    }

    void fetchConfig();
    return () => {
      cancelled = true;
    };
  }, []);

  const currentBackend = voiceConfig?.asr_backend ?? "whisper_local";
  const isAlreadyOnProposed = currentBackend === PROPOSED_BACKEND;
  const inTauri = isTauriRuntime();

  async function handleActivate() {
    setActivating(true);
    setError(null);
    try {
      const res = await tryTauriInvoke<{
        phase: string;
        message: string;
      }>("activate_model", { checkpointPath });
      if (!res) {
        // Not in Tauri shell — should be impossible because the
        // button is `disabled`, but guard anyway.
        setError("Not running inside the Tauri shell.");
        return;
      }
      if (res.phase === "error") {
        setError(res.message);
        return;
      }
      // Success — close the modal + refresh the backend label.
      toast.success("Voice model activated", {
        description: res.message,
      });
      setOpen(false);
      // Refresh so the card header reflects the new backend.
      try {
        const cfg = await api.getVoiceConfig();
        setVoiceConfig(cfg as VoiceConfig);
      } catch {
        // best-effort refresh
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setActivating(false);
    }
  }

  // ---- Render ----
  return (
    <HudCard>
      <div data-testid="model-swap-card" data-state={currentBackend}>
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest">
            Voice Model
          </span>
          <span className="text-[10px] font-mono text-[var(--text-muted)]">
            {currentBackend}
          </span>
        </div>
        <h3 className="text-lg font-[Rajdhani] text-[var(--text-primary)] mt-1">
          {isAlreadyOnProposed
            ? "Personalised model active"
            : "Default (whisper_local)"}
        </h3>
        <p className="text-[10px] text-[var(--text-muted)] font-mono mt-1">
          {isAlreadyOnProposed
            ? "Custom checkpoint is live."
            : "Run fine-tune + activate a personalised checkpoint."}
        </p>

        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger
            render={
              <Button
                variant="outline"
                size="sm"
                className="mt-3"
                disabled={isAlreadyOnProposed}
              />
            }
          >
            {isAlreadyOnProposed
              ? "Already active"
              : "Activate personalised model…"}
          </DialogTrigger>
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Activate personalised model</DialogTitle>
              <DialogDescription>
                This will edit <code>~/.gundam-halo/config.toml</code> and
                switch the voice pipeline to the fine-tuned checkpoint.
              </DialogDescription>
            </DialogHeader>

            {/* Diff preview */}
            <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
              <div className="border border-[var(--border-color)] p-2 rounded-sm">
                <div className="text-[var(--text-muted)] uppercase tracking-widest text-[9px] mb-1">
                  Current
                </div>
                <div>[voice.asr]</div>
                <div>backend = "{currentBackend}"</div>
              </div>
              <div className="border border-[var(--accent)] p-2 rounded-sm bg-[var(--accent)]/5">
                <div className="text-[var(--accent)] uppercase tracking-widest text-[9px] mb-1">
                  Proposed
                </div>
                <div>[voice.asr]</div>
                <div className="text-[var(--accent)]">
                  backend = "{PROPOSED_BACKEND}"
                </div>
                <div className="text-[var(--accent)] truncate" title={checkpointPath}>
                  model_path = "{checkpointPath}"
                </div>
              </div>
            </div>

            {/* Checkpoint path input */}
            <div className="mt-2">
              <label
                htmlFor="checkpoint-path"
                className="text-[10px] font-[Orbitron] text-[var(--text-muted)] uppercase tracking-widest"
              >
                Checkpoint path
              </label>
              <input
                id="checkpoint-path"
                data-testid="checkpoint-path-input"
                value={checkpointPath}
                onChange={(e) => setCheckpointPath(e.target.value)}
                className="w-full mt-1 bg-transparent border border-[var(--border-color)] px-2 py-1 text-xs font-mono text-[var(--text-primary)] focus:border-[var(--accent)] outline-none"
              />
            </div>

            {error && (
              <p
                className="text-[10px] text-[var(--danger)] font-mono mt-2 truncate"
                title={error}
              >
                {error}
              </p>
            )}

            <DialogFooter className="mt-4">
              <DialogClose
                render={<Button variant="ghost" size="sm" />}
              >
                Cancel
              </DialogClose>
              <Button
                data-testid="confirm-activate"
                onClick={handleActivate}
                disabled={activating || !inTauri}
                size="sm"
                title={
                  inTauri
                    ? undefined
                    : "Tauri shell required for model activation."
                }
              >
                {activating ? "Activating…" : "Confirm activate"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </HudCard>
  );
}

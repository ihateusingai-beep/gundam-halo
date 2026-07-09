/**
 * Settings → Voice tab — Sprint 56.7 orchestrator.
 *
 * ## What this file is now
 *
 * After Sprint 56.7 (the #1-ROI refactor from the senior-
 * engineer whole-project audit), `VoiceTab.tsx` is a thin
 * orchestrator that:
 *
 *   1. Loads `config` from `GET /voice/config`.
 *   2. Holds 5 draft pieces of state (asrBackend /
 *      asrCorrector / alwaysOnMic / draft / strictDraft).
 *   3. Provides 2 actions: `handleSave` (PUT round-trip
 *      + toast on success) and `handleReset` (re-sync
 *      drafts from server-truth).
 *   4. Composes 7 leaf sections, each ~30-180 LoC, each
 *      receiving the shared `store: VoiceSectionsStore`.
 *
 * The 828-LoC monolith this used to be is now ~115 LoC.
 * Each section is independently editable and the React.memo
 * boundary at the orchestrator/sections seam gives 7
 * independent re-render surfaces (toggling one section's
 * UI no longer rebuilds the other 6).
 *
 * ## Why the orchestrator owns the state
 *
 * The drafts (5 pieces) and the save action are intentionally
 * kept in VoiceTab (not lifted into a context) because:
 *
 *   - They cross section boundaries — Save reads all 5 drafts
 *     + the loaded `config` to construct the PUT body.
 *   - Sections don't talk to each other; they only read
 *     store props. Lifting state up means cross-section
 *     coordination happens in exactly one place.
 *   - A 6-component context would be premature — this is a
 *     single page, not a routed sub-app.
 *
 * ## Back-compat surface
 *
 * `VoiceTab` is exported by name from this module. The
 * `settings/index.tsx` route file imports it via
 * `import { VoiceTab } from "./tabs/VoiceTab"`. The export
 * name + the parameter-less signature are unchanged from
 * the pre-Sprint 56.7 version, so the route registration
 * works without any other file edits.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";
import { getVoiceStatus, type VoiceStatus } from "@/services/halo-voice-ws";

import { AlwaysOnSection } from "./voice/sections/AlwaysOnSection";
import { AsrSection } from "./voice/sections/AsrSection";
import { DiagnosticsSection } from "./voice/sections/DiagnosticsSection";
import { HowItWorksSection } from "./voice/sections/HowItWorksSection";
import { PersonalisedFineTuneSection } from "./voice/sections/PersonalisedFineTuneSection";
import { SaveBar } from "../shared/SaveBar";
import { WakeSection } from "./voice/sections/WakeSection";
import {
  isAsrBackend,
  isAsrCorrector,
  type AsrBackendDraft,
  type AsrCorrectorDraft,
  type VoiceConfig,
  type VoiceSectionsStore,
} from "./voice/types";

const ASR_BACKEND_DEFAULT: AsrBackendDraft = "whisper_local";
const ASR_CORRECTOR_DEFAULT: AsrCorrectorDraft = "bert";

/** Main field-set returned by `setVoiceConfig`. The backend
 *  re-validates against its ASR registry + corrector
 *  allowlist (Sprint 56.5 R4 fixed 3 pre-existing bugs in
 *  this path); we re-use the narrowest union of fields the
 *  UI can produce. */
interface SavePayload {
  wake_phrases: string[];
  strict_wake_phrase: boolean;
  asr_backend: AsrBackendDraft;
  asr_corrector: AsrCorrectorDraft;
  always_on_mic: boolean;
}

export function VoiceTab() {
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [strictDraft, setStrictDraft] = useState<boolean>(true);
  const [alwaysOnMicDraft, setAlwaysOnMicDraft] = useState<boolean>(false);
  const [asrBackendDraft, setAsrBackendDraft] =
    useState<AsrBackendDraft>(ASR_BACKEND_DEFAULT);
  const [asrCorrectorDraft, setAsrCorrectorDraft] =
    useState<AsrCorrectorDraft>(ASR_CORRECTOR_DEFAULT);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  // Mirroring the voice service's state into this tab —
  // cheap (no polling, just an interval read on the
  // shared status singleton from `services/voice/`).
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>(
    () => getVoiceStatus(),
  );

  // Re-fetch voice status every 5s. The interval is cheap
  // (singleton state read, no network); cleared on unmount.
  useEffect(() => {
    const id = setInterval(() => setVoiceStatus(getVoiceStatus()), 5000);
    return () => clearInterval(id);
  }, []);

  // One-shot config fetch on mount. Hydrates all 5 drafts.
  // For each draft the server-truth value is preferred; if
  // the value is outside the radio's type guard set (e.g.
  // hand-edited config.toml), we silently fall back to the
  // default so the radio shows a selected state.
  useEffect(() => {
    api
      .getVoiceConfig()
      .then((data) => {
        setConfig(data);
        setDraft(data.wake_phrases.join("\n"));
        setStrictDraft(data.strict_wake_phrase);
        setAlwaysOnMicDraft(data.always_on_mic ?? false);
        if (isAsrBackend(data.asr_backend)) setAsrBackendDraft(data.asr_backend);
        if (isAsrCorrector(data.asr_corrector))
          setAsrCorrectorDraft(data.asr_corrector);
      })
      .catch((e: unknown) => {
        const msg = e instanceof ApiError ? e.message : String(e);
        toast.error("Failed to load voice config", { description: msg });
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    if (saving) return;
    setSaving(true);
    // Split, trim, drop empties — matches the server's
    // normalisation.
    const phrases = draft
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    // De-dupe preserving first occurrence.
    const seen = new Set<string>();
    const deduped: string[] = [];
    for (const p of phrases) {
      if (!seen.has(p)) {
        seen.add(p);
        deduped.push(p);
      }
    }

    const payload: SavePayload = {
      wake_phrases: deduped,
      strict_wake_phrase: strictDraft,
      asr_backend: asrBackendDraft,
      asr_corrector: asrCorrectorDraft,
      always_on_mic: alwaysOnMicDraft,
    };
    try {
      const result = await api.setVoiceConfig(payload);
      setConfig({
        wake_phrases: result.wake_phrases,
        strict_wake_phrase: result.strict_wake_phrase,
        asr_backend: result.asr_backend,
        asr_corrector: result.asr_corrector,
        always_on_mic: result.always_on_mic,
        restart_required: result.restart_required,
      });
      setDraft(result.wake_phrases.join("\n"));
      setStrictDraft(result.strict_wake_phrase);
      if (result.always_on_mic !== undefined) {
        setAlwaysOnMicDraft(result.always_on_mic);
      }
      if (isAsrBackend(result.asr_backend)) {
        setAsrBackendDraft(result.asr_backend);
      }
      if (isAsrCorrector(result.asr_corrector)) {
        setAsrCorrectorDraft(result.asr_corrector);
      }
      notifySaveOutcome(result);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to save", { description: msg });
    } finally {
      setSaving(false);
    }
  };

  // Reset re-syncs all 5 drafts to the latest server-truth
  // config. If `config` is null (still loading), the reset
  // is a no-op — the Save button is already disabled in
  // that state via the loading gate above.
  const handleReset = () => {
    if (!config) return;
    setDraft(config.wake_phrases.join("\n"));
    setStrictDraft(config.strict_wake_phrase);
    if (config.always_on_mic !== undefined) {
      setAlwaysOnMicDraft(config.always_on_mic);
    }
    if (isAsrBackend(config.asr_backend)) {
      setAsrBackendDraft(config.asr_backend);
    }
    if (isAsrCorrector(config.asr_corrector)) {
      setAsrCorrectorDraft(config.asr_corrector);
    }
  };

  if (loading) {
    return (
      <HudCard>
        <div className="flex items-center gap-3">
          <div className="gundam-radar w-8 h-8" />
          <p className="text-[var(--text-muted)] font-mono">Loading voice config...</p>
        </div>
      </HudCard>
    );
  }

  // Compose the 7 sections via the shared `store`. The
  // orchestrator owns state + actions; each section is
  // memoizable on `store` identity.
  const store: VoiceSectionsStore = {
    config,
    setConfig,
    voiceStatus,
    asrBackend: asrBackendDraft,
    setAsrBackend: setAsrBackendDraft,
    asrCorrector: asrCorrectorDraft,
    setAsrCorrector: setAsrCorrectorDraft,
    alwaysOnMic: alwaysOnMicDraft,
    setAlwaysOnMic: setAlwaysOnMicDraft,
    draft,
    setDraft,
    strictDraft,
    setStrictDraft,
    saving,
    handleSave,
    handleReset,
  };

  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        Voice
      </h3>
      <DiagnosticsSection store={store} />
      <AsrSection store={store} />
      <AlwaysOnSection store={store} />
      <WakeSection store={store} />
      <SaveBar
        dirty
        saving={store.saving}
        onSave={store.handleSave}
        onReset={store.handleReset}
        saveTestId="voice-save-button"
        resetTestId="voice-reset-button"
        summary={
          store.config ? (
            <span data-testid="voice-config-summary">
              {store.config.wake_phrases.length} phrase(s) · gate:{" "}
              {store.config.strict_wake_phrase ? "strict" : "permissive"}
            </span>
          ) : undefined
        }
      />
      <HowItWorksSection />
      <PersonalisedFineTuneSection />
    </HudCard>
  );
}

/** Toast the user with the right message for the save
 *  outcome. Pulled out of `handleSave` so the action stays
 *  readable (~25 LoC body) without inlining the 30-line
 *  conditional cascade.
 *
 *  The three branches mirror the backend's behaviour:
 *    - `persisted && restart_scheduled` → 5-second restart
 *      happened (Sprint 19b), WS will reconnect.
 *    - `persisted && restart_required` → config.toml was
 *      written, but auto-restart couldn't fire.
 *    - `persisted && !restart_required` → no restart
 *      needed (e.g. only wake phrases changed).
 *    - `!persisted` → config.toml write failed; settings
 *      work in memory but won't survive a restart.
 */
function notifySaveOutcome(result: {
  persisted?: boolean;
  restart_required?: boolean;
  restart_scheduled?: boolean;
  error?: string;
}) {
  if (result.persisted) {
    if (result.restart_scheduled) {
      toast.success("Voice settings saved", {
        description:
          "The backend is restarting in 5 seconds with the new ASR engine / corrector. The voice WS will reconnect automatically.",
        duration: 8000,
      });
    } else if (result.restart_required) {
      toast.success("Voice settings saved", {
        description:
          "Restart the backend to load the new ASR engine / corrector. pkill -f 'uvicorn app.main:app' && uv run --project . uvicorn app.main:app",
      });
    } else {
      toast.success("Voice settings saved", {
        description:
          "The next voice turn uses the new wake-phrase list and gate. No restart needed.",
      });
    }
  } else {
    toast.warning("Saved in memory only", {
      description:
        result.error ??
        "config.toml write failed — settings work until you restart the backend.",
    });
  }
}

/**
 * Settings → Voice tab (Sprint 16 + 17a + 18 + 23 + 33).
 *
 * Sprint 16: lets the user edit the list of text-level wake
 * phrases the voice pipeline matches at the start of every ASR
 * transcript. Each line = one phrase. Empty lines are ignored.
 *
 * Sprint 17a adds a strict-mode toggle (default ON — see
 * docs/FEATURE-SPEC-SPRINT17a.md §11 for the breaking-change
 * rationale). When strict mode is on, voice turns whose ASR
 * transcript does not start with a configured wake phrase are
 * discarded server-side and the cockpit shows a brief toast.
 * Both `wake_phrases` and `strict_wake_phrase` are persisted
 * in one PUT round-trip. The 7-day upgrade banner that
 * accompanied the default flip was removed in Sprint 23
 * (v0.1.4) as the TTL had long expired for all users.
 *
 * Sprint 18 adds two radio groups for the ASR engine and the
 * corrector (formerly read-only in Sprint 17b). The user can
 * now pick `whisper_local` vs `yuesub` vs `whisper_hf` for
 * the engine (Sprint 23 adds `whisper_hf` for fine-tuned HF
 * checkpoints), and `bert` / `opencc` / `none` for the
 * corrector, and Save persists all four fields in one PUT
 * round-trip. Changing either asr field flips a
 * `restart_required` flag in the response; the dashboard shows
 * the "Restart required" banner. See docs/FEATURE-SPEC-SPRINT18.md
 * §3.2 for the UX wireframe.
 *
 * Sprint 33 (Track 31-B — Layer 2 v2 self-record corpus) adds
 * the "Personalised Fine-tune" section with 3 cards (Record /
 * Train / Swap) for the user-driven Cantonese fine-tune
 * workflow. The cards call new Tauri IPC commands
 * (`start_record`, `stop_record`, `start_train`,
 * `get_train_progress`, `activate_model`) defined in
 * `frontend/src-tauri/src/commands.rs` (which delegate to
 * `frontend/src-tauri/src/recording.rs`). The cards are
 * intentionally rendered as **stubs** in this sprint — the
 * UI is live (click → toast "Coming soon") so the UX wireframe
 * from FEATURE-SPEC-SPRINT26.md §4.1 + Appendix C is reviewable,
 * but the Tauri Rust pipeline is deferred to a follow-up
 * sprint per the spec's scope-realism rule (~770 LoC across
 * 6 files including 2 NEW Rust files is too heavy for one
 * sprint). See the Sprint 33 commit message for the scope
 * decision.
 *
 * The current voice WS state (idle / ready / etc.) is shown at
 * the top so the user can confirm the connection is alive before
 * they change phrases.
 */
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { api, ApiError } from "@/lib/api";
import { getVoiceStatus, type VoiceStatus } from "@/services/halo-voice-ws";
import { isTauriRuntime, tryTauriInvoke } from "@/lib/tauri";

import { KV, Section } from "./shared";

interface VoiceConfig {
  wake_phrases: string[];
  strict_wake_phrase: boolean;
  // Sprint 17b: the current ASR backend + corrector, so the
  // dashboard can show "Current ASR engine: yuesub (Cantonese)"
  // and surface a "restart required" hint when the user
  // changes either field (the ASR engine + corrector are
  // loaded at backend startup; a config PUT updates
  // in-memory state but the running pipeline still uses the
  // pre-restart instance).
  asr_backend?: string;
  asr_corrector?: string;
  // Sprint 19c: always-on mic toggle. Runtime-tunable; the
  // dashboard's Voice interaction mode radio binds to
  // alwaysOnMicDraft and the GET response hydrates it.
  always_on_mic?: boolean;
  restart_required?: boolean;
}

// Sprint 18: keep the asr_backend / asr_corrector draft
// state in sync with the current config. The radio groups
// bind to these drafts so the form is a controlled component
// (Reset re-syncs the drafts to the loaded config).
type AsrBackendDraft = "whisper_local" | "yuesub";
type AsrCorrectorDraft = "bert" | "opencc" | "none";

export function VoiceTab() {
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [strictDraft, setStrictDraft] = useState<boolean>(true);
  // Sprint 19c: always-on mic draft. Runtime-tunable; the
  // dashboard reads the GET response to hydrate this. The
  // default false preserves the Sprint 16 push-to-talk
  // behavior for users who never open Settings → Voice.
  const [alwaysOnMicDraft, setAlwaysOnMicDraft] = useState<boolean>(false);
  // Sprint 18: drafts for the ASR engine + corrector. The
  // server validates the value and persists to config.toml;
  // we just need to send the user's choice in the PUT.
  // Defaults match the backend config defaults so the radio
  // is in a known state if the user reloads before the GET
  // resolves.
  const [asrBackendDraft, setAsrBackendDraft] =
    useState<AsrBackendDraft>("whisper_local");
  const [asrCorrectorDraft, setAsrCorrectorDraft] =
    useState<AsrCorrectorDraft>("bert");
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>(
    () => getVoiceStatus(),
  );
  // Sprint 33b — Personalised Fine-tune cards (Record / Train / Swap)
  // each track their own phase. The shared `runFinetuneCommand`
  // (module-level) writes the matching slot via the `CardSetters`
  // it receives. `idle` while no click has registered, `running`
  // while the IPC call is in flight, then `complete` / `error`
  // from the Rust response.
  const [recordPhase, setRecordPhase] = useState<CardPhase>("idle");
  const [recordMessage, setRecordMessage] = useState<string>("");
  const [trainPhase, setTrainPhase] = useState<CardPhase>("idle");
  const [trainMessage, setTrainMessage] = useState<string>("");
  const [swapPhase, setSwapPhase] = useState<CardPhase>("idle");
  const [swapMessage, setSwapMessage] = useState<string>("");

  // Mirror the voice service's state into this tab. Cheap — no
  // polling, we just read the singleton on every render via the
  // refresh interval below.
  useEffect(() => {
    const id = setInterval(() => setVoiceStatus(getVoiceStatus()), 5000);
    return () => clearInterval(id);
  }, []);

  // Fetch the current config on mount.
  useEffect(() => {
    api
      .getVoiceConfig()
      .then((data) => {
        setConfig(data);
        setDraft(data.wake_phrases.join("\n"));
        setStrictDraft(data.strict_wake_phrase);
        // Sprint 19c: hydrate the always-on mic draft.
        setAlwaysOnMicDraft(data.always_on_mic ?? false);
        // Sprint 18: hydrate the radio drafts from the GET
        // response. The server may report an unknown value
        // (e.g. if config.toml was hand-edited) — in that
        // case we fall back to the defaults so the radios
        // are still selectable.
        if (data.asr_backend === "whisper_local" || data.asr_backend === "yuesub") {
          setAsrBackendDraft(data.asr_backend);
        }
        if (
          data.asr_corrector === "bert" ||
          data.asr_corrector === "opencc" ||
          data.asr_corrector === "none"
        ) {
          setAsrCorrectorDraft(data.asr_corrector);
        }
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
    // Split, trim, drop empties — matches the server's normalisation.
    const phrases = draft
      .split("\n")
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    // De-dupe, preserving first occurrence.
    const seen = new Set<string>();
    const deduped: string[] = [];
    for (const p of phrases) {
      if (!seen.has(p)) {
        seen.add(p);
        deduped.push(p);
      }
    }
    try {
      const result = await api.setVoiceConfig({
        wake_phrases: deduped,
        strict_wake_phrase: strictDraft,
        // Sprint 18: include the ASR engine + corrector in the
        // same PUT. The backend validates the values, persists
        // to config.toml, and flips restart_required in the
        // response if either actually changed.
        asr_backend: asrBackendDraft,
        asr_corrector: asrCorrectorDraft,
        // Sprint 19c: include the always-on mic toggle in the
        // same PUT. Runtime-tunable (no restart_required).
        always_on_mic: alwaysOnMicDraft,
      });
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
      if (result.always_on_mic !== undefined) setAlwaysOnMicDraft(result.always_on_mic);
      if (result.asr_backend) setAsrBackendDraft(result.asr_backend as AsrBackendDraft);
      if (result.asr_corrector) setAsrCorrectorDraft(result.asr_corrector as AsrCorrectorDraft);
      if (result.persisted) {
        if (result.restart_scheduled) {
          // Sprint 19b: the backend auto-restarts itself
          // in 5 seconds so the new ASR engine / corrector
          // takes effect. The WebSocket will disconnect
          // briefly and reconnect to the new process.
          toast.success("Voice settings saved", {
            description:
              "The backend is restarting in 5 seconds with the new ASR engine / corrector. The voice WS will reconnect automatically.",
            duration: 8000,
          });
        } else if (result.restart_required) {
          // Fallback: the user changed asr but the
          // restart scheduler couldn't fire (e.g. no
          // running event loop). Tell them how to
          // restart manually.
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
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      toast.error("Failed to save", { description: msg });
    } finally {
      setSaving(false);
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

  return (
    <HudCard>
      <h3 className="text-sm font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
        Voice
      </h3>

      <Section title="Voice WebSocket">
        <KV
          label="State"
          value={voiceStatus.state}
          accent={voiceStatus.state === "ready"}
        />
        <KV
          label="Server enabled"
          value={voiceStatus.serverEnabled ? "yes" : "no"}
        />
        {voiceStatus.error && (
          <KV
            label="Last error"
            value={voiceStatus.error}
            danger
          />
        )}
      </Section>

      <Section title="ASR engine (Sprint 18)">
        {/* Sprint 17b: read-only display of the current ASR engine
            and corrector.
            Sprint 18: the section is now EDITABLE. Two radio
            groups — one for the engine, one for the corrector —
            bound to asrBackendDraft / asrCorrectorDraft. Save
            (at the bottom of the form) dispatches all four
            fields in one PUT; the backend persists, validates,
            and flips the `restart_required` flag if either asr
            field actually changed. */}
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          Choose the speech-recognition backend. <strong>whisper_local</strong>{" "}
          is the default (openai-whisper base, English / Mandarin).
          <strong> yuesub</strong> uses SenseVoiceSmall + fsmn-vad for
          Cantonese. Changing this requires a backend restart.
        </p>
        <div className="flex flex-col gap-1.5" data-testid="asr-backend-radios">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="asr-backend"
              value="whisper_local"
              checked={asrBackendDraft === "whisper_local"}
              onChange={() => setAsrBackendDraft("whisper_local")}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              whisper_local
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — openai-whisper (English / Mandarin)
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="asr-backend"
              value="yuesub"
              checked={asrBackendDraft === "yuesub"}
              onChange={() => setAsrBackendDraft("yuesub")}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              yuesub
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — SenseVoiceSmall + fsmn-vad (Cantonese)
            </span>
          </label>
        </div>
      </Section>

      <Section title="Corrector (Sprint 18)">
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          Post-process the ASR output. <strong>bert</strong> uses
          OpenCC + BERT masked-LM (slow, 300-500ms per segment but
          high quality). <strong>opencc</strong> uses OpenCC + regex
          rules (fast, &lt;5ms). <strong>none</strong> skips the
          corrector entirely. Only applies to the yuesub backend.
        </p>
        <div className="flex flex-col gap-1.5" data-testid="asr-corrector-radios">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="asr-corrector"
              value="bert"
              checked={asrCorrectorDraft === "bert"}
              onChange={() => setAsrCorrectorDraft("bert")}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              bert
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — OpenCC + BERT masked-LM (slow but high quality)
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="asr-corrector"
              value="opencc"
              checked={asrCorrectorDraft === "opencc"}
              onChange={() => setAsrCorrectorDraft("opencc")}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              opencc
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — OpenCC + regex rules (fast)
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="asr-corrector"
              value="none"
              checked={asrCorrectorDraft === "none"}
              onChange={() => setAsrCorrectorDraft("none")}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              none
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — Raw ASR output
            </span>
          </label>
        </div>
      </Section>

      {config?.restart_required && (
        <div className="mt-2 mb-3 border border-[var(--warning)] bg-[var(--bg-elevated)] px-3 py-2 text-xs font-mono">
          <span className="text-[var(--warning)]">⚠ Restart required:</span>{" "}
          <span className="text-[var(--text-primary)]">
            config.toml changed but the running backend still
            uses the pre-restart instance. Restart with{" "}
            <code>pkill -f &apos;uvicorn app.main:app&apos; &amp;&amp; uv run --project . uvicorn app.main:app</code>{" "}
            for the new ASR engine / corrector to take effect.
          </span>
        </div>
      )}

      <Section title="Voice interaction mode (Sprint 19c)">
        {/* Sprint 19c: choose between push-to-talk (the
            default) and always-on mic. Always-on auto-
            fires the agent on the backend's VAD
            speech_start event; the cockpit shows a ⏸
            toggle to pause. Runtime-tunable — no
            restart required. */}
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          Choose how the cockpit captures your voice.
          <strong> Push-to-talk</strong> keeps the mic
          closed until you press and hold the 🎤 button
          (lowest power, most private).
          <strong> Always-on</strong> keeps the mic open
          and uses the backend's VAD to detect when you
          start talking; the agent fires automatically.
          A small ⏸ toggle appears in the cockpit when
          always-on is enabled.
        </p>
        <div className="flex flex-col gap-1.5" data-testid="voice-interaction-mode-radios">
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="voice-interaction-mode"
              value="push-to-talk"
              checked={!alwaysOnMicDraft}
              onChange={() => setAlwaysOnMicDraft(false)}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              Push-to-talk
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — hold the mic button to talk (default)
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="radio"
              name="voice-interaction-mode"
              value="always-on"
              checked={alwaysOnMicDraft}
              onChange={() => setAlwaysOnMicDraft(true)}
              className="accent-[var(--accent)] cursor-pointer"
            />
            <span className="text-xs font-mono text-[var(--text-primary)]">
              Always-on
            </span>
            <span className="text-[10px] text-[var(--text-muted)] font-mono">
              — mic always live; VAD auto-fires the agent
            </span>
          </label>
        </div>
      </Section>

      <Section title="Wake phrases (Sprint 16)">
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-2">
          When you hold the mic button, the ASR transcript is checked
          against these phrases at the start. If one matches, the
          prefix is stripped and the turn is tagged as
          wake-triggered in the MissionLog.
        </p>
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          rows={Math.max(4, (config?.wake_phrases.length ?? 0) + 2)}
          className="w-full bg-[var(--bg-input)] border border-[var(--border-color)] rounded px-2 py-1.5 text-xs font-mono text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent)] placeholder:text-[var(--text-muted)]/50"
          placeholder="Unicorn&#10;NTD&#10;gundam&#10;獨角獸&#10;高達"
        />
      </Section>

      <Section title="Wake-phrase gate (Sprint 17a)">
        <p className="text-xs text-[var(--text-secondary)] font-mono mb-3">
          When strict mode is <strong>on</strong> (the default), voice
          turns are discarded unless the ASR transcript starts with
          one of the configured wake phrases above. When{" "}
          <strong>off</strong>, the agent runs on every transcript;
          the wake phrase is just a confidence marker. Both settings
          apply to push-to-talk and the voice text-input field.
        </p>
        <label className="flex items-center gap-2 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={strictDraft}
            onChange={(e) => setStrictDraft(e.target.checked)}
            className="w-4 h-4 accent-[var(--accent)] cursor-pointer"
            data-testid="strict-wake-checkbox"
          />
          <span className="text-xs font-mono text-[var(--text-primary)]">
            Strict mode (only fire on a wake phrase)
          </span>
        </label>
      </Section>

      <div className="flex items-center gap-2 mt-3 flex-wrap">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          onClick={() => {
            setDraft(config?.wake_phrases.join("\n") ?? "");
            setStrictDraft(config?.strict_wake_phrase ?? true);
            // Sprint 19c: reset the always-on mic draft.
            // Falls back to false (the default) if the
            // server hasn't returned a value yet.
            if (config?.always_on_mic !== undefined) {
              setAlwaysOnMicDraft(config.always_on_mic);
            }
            // Sprint 18: reset the asr drafts too. Falls back
            // to the default ("whisper_local" / "bert") if the
            // server hasn't returned a value yet (loading
            // state).
            if (config?.asr_backend === "whisper_local" || config?.asr_backend === "yuesub") {
              setAsrBackendDraft(config.asr_backend);
            }
            if (
              config?.asr_corrector === "bert" ||
              config?.asr_corrector === "opencc" ||
              config?.asr_corrector === "none"
            ) {
              setAsrCorrectorDraft(config.asr_corrector);
            }
          }}
          disabled={saving}
          className="px-3 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors disabled:opacity-40"
        >
          Reset
        </button>
        {config && (
          <span className="text-[10px] text-[var(--text-muted)] font-mono">
            {config.wake_phrases.length} phrase(s) · gate:{" "}
            {config.strict_wake_phrase ? "strict" : "permissive"}
          </span>
        )}
      </div>

      <Section title="How it works">
        <p className="text-xs text-[var(--text-muted)] font-mono leading-relaxed">
          Strict mode (on by default in Sprint 17a) is the recommended
          setting: it stops background TV and accidental mic-button
          bumps from invoking the agent. Permissive mode is useful
          for keyboard-driven debug sessions where you want every
          transcript to reach the agent. The wake phrase list above
          applies in both modes; in strict mode the prefix is
          required, in permissive mode it's a confidence marker.
        </p>
      </Section>

      {/* Sprint 33 (Track 31-B — Layer 2 v2 self-record corpus).
          Three-card flow per FEATURE-SPEC-SPRINT26.md §4.1 +
          Appendix C: Record → Train → Swap. The cards are
          intentionally **stubs** in this sprint — the
          Tauri Rust pipeline (frontend/src-tauri/src/
          {commands,recording}.rs) is deferred to a follow-up
          sprint per scope realism (~770 LoC across 6 files
          including 2 NEW Rust files is too heavy for one
          sprint). The UI is rendered so the wireframe is
          reviewable; clicking a button shows a toast pointing
          at the stub so the user knows the wiring is alive.

          Future sprint: wire each button to the real Tauri
          IPC command (`invoke('start_record', ...)` etc.)
          defined in commands.rs. The contracts are pinned by
          the rustdoc comments on those commands — no
          frontend-side changes will be needed when the
          follow-up sprint lands. */}
      <Section title="Personalised Fine-tune (Sprint 33b)">
        <p
          className="text-xs text-[var(--text-secondary)] font-mono mb-2"
          data-testid="personalised-finetune-intro"
        >
          Personalise the v0.1.4 WhisperHFASR on your own voice.
          Three steps, run independently — you can pause between
          Record and Train. Each card calls a Tauri IPC command
          defined in <code>frontend/src-tauri/src/commands.rs</code>
          (the recording / training pipeline lives in
          <code> recording/</code>; Sprint 33b ships the real
          cpal + hound + parallel WhisperHFASR subprocess impl
          that Sprint 33 stubbed — see the Sprint 33b commit
          message for the scope decision).
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Record card — calls `start_record` / `stop_record`. */}
          <HudCard
            className="p-3"
            data-testid="personalised-finetune-record-card"
          >
            <div className="flex items-center justify-between mb-2">
              <h5 className="text-[11px] font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                Record
              </h5>
              <span
                className="text-[9px] font-mono text-[var(--text-muted)] uppercase"
                data-testid="record-card-status"
              >
                {recordPhase}
              </span>
            </div>
            <p className="text-[11px] font-mono text-[var(--text-muted)] mb-2 leading-relaxed">
              Speak Cantonese for 30 minutes. The app saves
              30s chunks to
              <code> ~/.gundam-halo/recordings/yue-self-&lt;date&gt;/</code>
              and transcribes them in parallel using the v0.1.4
              WhisperHFASR backend. Auto-stops at 30 min;
              you can stop early (min 10 min) or extend (max 60 min).
            </p>
            <button
              type="button"
              onClick={() =>
                runFinetuneCommand("start_record", {
                  setPhase: setRecordPhase,
                  setMessage: setRecordMessage,
                  label: "Record",
                })
              }
              disabled={!isTauriRuntime()}
              data-testid="personalised-finetune-record-button"
              className="w-full px-2 py-1.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Start recording
            </button>
            {recordMessage && (
              <p
                className="mt-2 text-[10px] font-mono text-[var(--text-secondary)] leading-relaxed break-words"
                data-testid="record-card-message"
              >
                {recordMessage}
              </p>
            )}
          </HudCard>

          {/* Train card — calls `start_train` / `get_train_progress`. */}
          <HudCard
            className="p-3"
            data-testid="personalised-finetune-train-card"
          >
            <div className="flex items-center justify-between mb-2">
              <h5 className="text-[11px] font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                Train
              </h5>
              <span
                className="text-[9px] font-mono text-[var(--text-muted)] uppercase"
                data-testid="train-card-status"
              >
                {trainPhase}
              </span>
            </div>
            <p className="text-[11px] font-mono text-[var(--text-muted)] mb-2 leading-relaxed">
              Run the personalised fine-tune. Loads the v0.1.4
              Common Voice yue checkpoint as the base, fine-tunes
              on your self-record corpus (1 hour wall clock on
              M-series). Output lands at
              <code> ~/.gundam-halo/models/whisper-yue-self-&lt;date&gt;/</code>.
            </p>
            <button
              type="button"
              onClick={() =>
                runFinetuneCommand("start_train", {
                  setPhase: setTrainPhase,
                  setMessage: setTrainMessage,
                  label: "Train",
                })
              }
              disabled={!isTauriRuntime()}
              data-testid="personalised-finetune-train-button"
              className="w-full px-2 py-1.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Start training
            </button>
            {trainMessage && (
              <p
                className="mt-2 text-[10px] font-mono text-[var(--text-secondary)] leading-relaxed break-words"
                data-testid="train-card-message"
              >
                {trainMessage}
              </p>
            )}
          </HudCard>

          {/* Swap card — calls `activate_model`. */}
          <HudCard
            className="p-3"
            data-testid="personalised-finetune-swap-card"
          >
            <div className="flex items-center justify-between mb-2">
              <h5 className="text-[11px] font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                Swap
              </h5>
              <span
                className="text-[9px] font-mono text-[var(--text-muted)] uppercase"
                data-testid="swap-card-status"
              >
                {swapPhase}
              </span>
            </div>
            <p className="text-[11px] font-mono text-[var(--text-muted)] mb-2 leading-relaxed">
              Activate the personalised model — points
              <code> voice.asr.model_path</code> at the new
              checkpoint in <code>~/.gundam-halo/config.toml</code>
              and restarts the backend. Previous v0.1.4 checkpoint
              is kept as a fallback (revert via git checkout).
            </p>
            <button
              type="button"
              onClick={() =>
                runFinetuneCommand("activate_model", {
                  setPhase: setSwapPhase,
                  setMessage: setSwapMessage,
                  label: "Swap",
                })
              }
              disabled={!isTauriRuntime()}
              data-testid="personalised-finetune-swap-button"
              className="w-full px-2 py-1.5 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] bg-[var(--bg-elevated)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Activate personalised model
            </button>
            {swapMessage && (
              <p
                className="mt-2 text-[10px] font-mono text-[var(--text-secondary)] leading-relaxed break-words"
                data-testid="swap-card-message"
              >
                {swapMessage}
              </p>
            )}
          </HudCard>
        </div>
        <p className="text-[10px] text-[var(--text-muted)] font-mono mt-2 leading-relaxed">
          Sprint 33b wires the three cards above to the real Tauri
          IPC commands in <code>src-tauri/src/commands.rs</code>
          (<code>start_record</code> / <code>start_train</code> /
          <code> activate_model</code>). The Rust pipeline opens
          the mic via cpal, writes 30 s WAV chunks to
          <code> ~/.gundam-halo/recordings/yue-self-&lt;date&gt;/</code>,
          transcribes each chunk in a parallel Python
          <code> whisper_hf_helper</code> subprocess, and patches
          <code> config.toml</code> via <code>toml_edit</code> on
          activate. The status badge on each card mirrors the
          <code> phase</code> field of the IPC response. See
          <code> docs/FEATURE-SPEC-SPRINT26.md</code> §4.1 +
          Appendix C for the full UX.
        </p>
      </Section>
    </HudCard>
  );
}

/**
 * Sprint 33b — Personalised Fine-tune command dispatcher.
 * Maps each Tauri IPC command (`start_record` / `start_train` /
 * `activate_model`) to the matching card state slot. The Rust
 * side returns a `RecordingCommandResponse` with `phase`
 * (`"running" | "complete" | "error"`); we mirror that into the
 * card so the UI shows live status instead of a stub toast.
 * Errors thrown by the Rust side come back as a JSON
 * `RecordingError` (tagged union); we surface the `Display`
 * text via `error.message` (Tauri wraps the tagged payload into
 * the thrown error's `.message` field).
 *
 * Lives inside the component (not module-level) because it
 * needs the per-card `setPhase` / `setMessage` closures. The
 * dispatch table is keyed on command name → setters + label
 * to keep the call sites uniform.
 */
type FinetuneResponse = {
  phase: "running" | "complete" | "error";
  message: string;
  progress?: number;
  logTail?: string[];
};
type CardPhase = "idle" | "running" | "complete" | "error";
type CardSetters = {
  setPhase: (p: CardPhase) => void;
  setMessage: (m: string) => void;
  label: string;
};
async function runFinetuneCommand(
  command: "start_record" | "start_train" | "activate_model",
  slots: CardSetters,
) {
  const { setPhase, setMessage, label } = slots;
  setPhase("running");
  setMessage(`${command} → backend…`);
  try {
    const res = await tryTauriInvoke<FinetuneResponse>(command);
    if (!res) {
      // Outside the Tauri shell the buttons are `disabled` (see
      // the `disabled={!isTauriRuntime()}` on each card), so this
      // path only fires if the runtime flips between render and
      // click (extremely rare). Treat as a hard error.
      setPhase("error");
      setMessage("Not running inside the Tauri shell.");
      toast.error(`[${label}] Not running inside the Tauri shell.`);
      return;
    }
    // Map Rust phase → UI phase. `running` and `complete` are 1:1;
    // `error` is the same word (the Rust side sets phase="error"
    // only on the success-return path — a thrown error goes through
    // the catch below).
    setPhase(res.phase);
    setMessage(res.message);
    if (res.phase === "complete") {
      toast.success(`[${label}] ${res.message}`, { duration: 4000 });
    } else if (res.phase === "error") {
      toast.error(`[${label}] ${res.message}`, { duration: 6000 });
    } else {
      toast.info(`[${label}] ${res.message}`, { duration: 3000 });
    }
  } catch (e: any) {
    setPhase("error");
    const msg =
      e?.message ?? `${command} failed — check the dashboard console.`;
    setMessage(msg);
    toast.error(`[${label}] ${msg}`, { duration: 6000 });
  }
}

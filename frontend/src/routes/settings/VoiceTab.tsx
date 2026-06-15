/**
 * Settings → Voice tab (Sprint 16 + 17a + 18).
 *
 * Sprint 16: lets the user edit the list of text-level wake
 * phrases the voice pipeline matches at the start of every ASR
 * transcript. Each line = one phrase. Empty lines are ignored.
 *
 * Sprint 17a adds a strict-mode toggle (default ON — see
 * docs/FEATURE-SPEC-SPRINT17a.md §11 for the breaking-change
 * rationale and the 7-day upgrade-banner mitigation). When
 * strict mode is on, voice turns whose ASR transcript does not
 * start with a configured wake phrase are discarded server-side
 * and the cockpit shows a brief toast. Both `wake_phrases` and
 * `strict_wake_phrase` are persisted in one PUT round-trip.
 *
 * Sprint 18 adds two radio groups for the ASR engine and the
 * corrector (formerly read-only in Sprint 17b). The user can
 * now pick `whisper_local` vs `yuesub` for the engine, and
 * `bert` / `opencc` / `none` for the corrector, and Save
 * persists all four fields in one PUT round-trip. Changing
 * either asr field flips a `restart_required` flag in the
 * response; the dashboard shows the "Restart required"
 * banner. See docs/FEATURE-SPEC-SPRINT18.md §3.2 for the
 * UX wireframe.
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
  restart_required?: boolean;
}

// Sprint 18: keep the asr_backend / asr_corrector draft
// state in sync with the current config. The radio groups
// bind to these drafts so the form is a controlled component
// (Reset re-syncs the drafts to the loaded config).
type AsrBackendDraft = "whisper_local" | "yuesub";
type AsrCorrectorDraft = "bert" | "opencc" | "none";

const UPGRADE_BANNER_KEY = "halo.voice.strict-banner-dismissed-at";
const UPGRADE_BANNER_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

function shouldShowUpgradeBanner(): boolean {
  // Sprint 17a §11: show the strict-mode upgrade banner for 7
  // days after the user first sees it, or until they dismiss it.
  // We persist the dismissal timestamp in localStorage so the
  // banner stays gone across reloads.
  if (typeof window === "undefined") return false;
  try {
    const raw = window.localStorage.getItem(UPGRADE_BANNER_KEY);
    if (raw) {
      const dismissedAt = Number.parseInt(raw, 10);
      if (Number.isFinite(dismissedAt)) {
        if (Date.now() - dismissedAt < UPGRADE_BANNER_TTL_MS) {
          return false;
        }
      }
    }
  } catch {
    // localStorage may be disabled (private mode, etc.) — show
    // the banner anyway; it just won't be persisted.
  }
  return true;
}

function dismissUpgradeBanner(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(UPGRADE_BANNER_KEY, String(Date.now()));
  } catch {
    // ignore — the banner will re-appear next page load but the
    // user has at least dismissed this one.
  }
}

export function VoiceTab() {
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [strictDraft, setStrictDraft] = useState<boolean>(true);
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
  const [showUpgradeBanner, setShowUpgradeBanner] = useState(false);

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

  // Sprint 17a §11: show the strict-mode upgrade banner on first
  // visit after the upgrade. Hidden after dismiss OR after 7 days.
  useEffect(() => {
    if (config !== null && shouldShowUpgradeBanner()) {
      setShowUpgradeBanner(true);
    }
  }, [config]);

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
      });
      setConfig({
        wake_phrases: result.wake_phrases,
        strict_wake_phrase: result.strict_wake_phrase,
        asr_backend: result.asr_backend,
        asr_corrector: result.asr_corrector,
        restart_required: result.restart_required,
      });
      setDraft(result.wake_phrases.join("\n"));
      setStrictDraft(result.strict_wake_phrase);
      if (result.asr_backend) setAsrBackendDraft(result.asr_backend as AsrBackendDraft);
      if (result.asr_corrector) setAsrCorrectorDraft(result.asr_corrector as AsrCorrectorDraft);
      if (result.persisted) {
        if (result.restart_required) {
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

      {/* Sprint 17a §11: 7-day upgrade banner for the strict-mode
          default flip. Shown until dismissed OR 7 days pass. */}
      {showUpgradeBanner && (
        <div
          className="mb-4 border border-[var(--accent)] bg-[var(--bg-elevated)] px-3 py-2 text-xs font-mono"
          role="status"
        >
          <div className="flex items-start gap-2">
            <span className="text-[var(--accent)] shrink-0">⚠</span>
            <div className="flex-1">
              <p className="text-[var(--text-primary)] mb-1">
                <strong>New in Sprint 17a:</strong> Strict wake-phrase
                mode is now on by default. Voice turns need a wake
                phrase (e.g. <code>Unicorn</code>, <code>高達</code>)
                to invoke the agent. To revert to permissive mode,
                uncheck the box below.
              </p>
              <div className="flex gap-2 mt-2">
                <button
                  onClick={() => {
                    setStrictDraft(false);
                    dismissUpgradeBanner();
                    setShowUpgradeBanner(false);
                    toast.info(
                      "Strict mode will be disabled when you click Save.",
                    );
                  }}
                  className="px-2 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--bg-primary)] transition-colors"
                >
                  Open Settings
                </button>
                <button
                  onClick={() => {
                    dismissUpgradeBanner();
                    setShowUpgradeBanner(false);
                  }}
                  className="px-2 py-1 text-[10px] uppercase tracking-wider font-[Rajdhani] border border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
    </HudCard>
  );
}

/**
 * Audio graph — single AudioContext + EQ filter chain for TTS
 * playback.
 *
 * Sprint 57 NEW. VoicePanel's TTS chunks (MP3 from edge-tts) are
 * played via an `<audio>` element. We want to apply per-theme EQ
 * BEFORE the audio reaches the speakers. The standard pattern:
 *
 *   <audio> → MediaElementAudioSourceNode
 *            → BiquadFilter (band 1: 100 Hz low shelf)
 *            → BiquadFilter (band 2: 250 Hz peaking)
 *            → BiquadFilter (band 3: 1 kHz peaking)
 *            → BiquadFilter (band 4: 2.5 kHz peaking)
 *            → BiquadFilter (band 5: 6 kHz high shelf)
 *            → AudioDestinationNode (speakers)
 *
 * The graph is created **once per AudioContext** and shared
 * across all `playChunk()` calls — the EQ chain doesn't change
 * per chunk, only per theme. When the user switches theme, we
 * call `applyEqPreset(filters, newPreset)` (no need to rebuild
 * the graph).
 *
 * ## Why 1 AudioContext per VoicePanel?
 *
 * Modern browsers limit the number of AudioContexts (Chromium:
 * ~6 per page, Firefox: ~30+). VoicePanel is the only consumer
 * of audio playback in this codebase, so 1 is plenty. The
 * AudioContext is lazy-initialized on first `playChunk` (i.e. on
 * the first TTS audio frame) — the `user-gesture` requirement
 * for AudioContext.resume() is satisfied because the user has
 * already pressed the mic button or triggered a voice turn by
 * the time TTS audio arrives.
 *
 * ## Why MP3 via MediaElementAudioSourceNode?
 *
 * `MediaElementAudioSourceNode` accepts an `<audio>` element as
 * a source. The audio data (MP3) is decoded by the browser
 * automatically. This is the simplest path: we don't have to
 * decode the MP3 in JavaScript (which would require an MP3
 * decoder library + ~30 KB of WASM), and we get to keep the
 * existing `<audio>`-element-based playback (with seek, pause,
 * volume control, fullscreen video if needed) for free.
 *
 * ## Why per-theme EQ on output and not on input?
 *
 * TTS audio is what the **agent** is saying — it's our
 * (Gundam Halo's) voice, not the user's. We apply the EQ to
 * the OUTPUT (the agent's voice) so each theme has its own sonic
 * character. The user's mic input is unaffected (the
 * `useVoiceInput` / `use-mic-analyser` hook chain is independent).
 */
import { applyEqPreset, getEqPreset, type EqPreset } from "./audio-eq";

/** A self-contained audio graph (1 AudioContext + 5 EQ filters)
 *  used by VoicePanel for TTS playback. Created once on the
 *  first playChunk; reused for every subsequent chunk. */
export class TtsAudioGraph {
  private ctx: AudioContext | null = null;
  private filters: BiquadFilterNode[] = [];
  private source: MediaElementAudioSourceNode | null = null;
  private currentPreset: EqPreset = getEqPreset(null);
  private mediaElement: HTMLAudioElement | null = null;

  /** Get the underlying AudioContext (lazy-initialized on first
   *  call). Returns null if Web Audio API is unavailable
   *  (e.g. in jsdom or some test environments). */
  getContext(): AudioContext | null {
    if (this.ctx) return this.ctx;
    if (typeof window === "undefined") return null;
    const Ctor =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctor) return null;
    this.ctx = new Ctor();
    // Build the 5-band filter chain. Filters are connected in
    // series; the source node will be patched in via
    // `attachMediaElement`. The chain starts at filter[0] and
    // ends at `ctx.destination` (the speakers).
    this.filters = [0, 1, 2, 3, 4].map(() => this.ctx!.createBiquadFilter());
    for (let i = 0; i < 4; i++) {
      this.filters[i].connect(this.filters[i + 1]);
    }
    this.filters[4].connect(this.ctx.destination);
    // Apply the current preset (default = flat).
    applyEqPreset(this.filters, this.currentPreset);
    return this.ctx;
  }

  /** Attach an `<audio>` element to the graph. The element's
   *  audio output is now routed through the EQ chain instead of
   *  going directly to the speakers. Call this once per
   *  `<audio>` element (VoicePanel uses 1 shared element). */
  attachMediaElement(audio: HTMLAudioElement): void {
    const ctx = this.getContext();
    if (!ctx) return;
    if (this.source) {
      // Re-attaching a different element requires disconnecting
      // the previous source. We don't expect this in practice
      // (VoicePanel uses 1 element for the lifetime of the
      // component) but the guard keeps the graph honest.
      this.source.disconnect();
    }
    if (this.mediaElement && this.mediaElement !== audio) {
      this.mediaElement.src = "";
    }
    this.source = ctx.createMediaElementSource(audio);
    this.source.connect(this.filters[0]);
    this.mediaElement = audio;
  }

  /** Apply a theme's EQ preset to the existing filter chain.
   *  No-op if (a) the graph hasn't been initialized yet, or
   *  (b) the new theme is the same as the last one applied.
   *  The "same theme" check is a tiny optimization but it also
   *  documents the contract: callers can safely call setTheme
   *  on every TTS chunk without re-applying the same preset
   *  10 times in a row. */
  setTheme(themeId: string | null): void {
    const newPreset = getEqPreset(themeId);
    if (newPreset === this.currentPreset) return;
    this.currentPreset = newPreset;
    if (this.filters.length === 5) {
      applyEqPreset(this.filters, this.currentPreset);
    }
  }

  /** Sprint 62 A-A2: set the EQ preset directly (bypasses the
   *  theme lookup). Used by `useEqStore` for the per-USER
   *  override — the user picks a theme for visuals but a
   *  different preset for audio. After `setPreset(p)`, the
   *  next `setTheme(...)` call would re-resolve from the
   *  theme (overriding the override); the caller (the
   *  store) re-applies the override as needed. */
  setPreset(preset: EqPreset): void {
    if (preset === this.currentPreset) return;
    this.currentPreset = preset;
    if (this.filters.length === 5) {
      applyEqPreset(this.filters, this.currentPreset);
    }
  }

  /** Current preset (useful for the visualizer). */
  getPreset(): EqPreset {
    return this.currentPreset;
  }

  /** The 5 live BiquadFilterNodes (for visualization that reads
   *  the actual `frequency` / `gain` values). Returns [] if the
   *  graph hasn't been initialized. */
  getFilters(): BiquadFilterNode[] {
    return this.filters;
  }

  /** Resume the AudioContext (needed after a `suspend` from
   *  tab visibility change). Idempotent — safe to call
   *  repeatedly. */
  async resume(): Promise<void> {
    const ctx = this.getContext();
    if (ctx && ctx.state === "suspended") {
      await ctx.resume();
    }
  }

  /** Tear down: disconnect everything and close the AudioContext.
   *  Called on VoicePanel unmount to avoid leaking the context
   *  across hot-reloads. */
  async dispose(): Promise<void> {
    if (this.source) {
      this.source.disconnect();
      this.source = null;
    }
    for (const f of this.filters) {
      f.disconnect();
    }
    this.filters = [];
    if (this.ctx && this.ctx.state !== "closed") {
      await this.ctx.close();
    }
    this.ctx = null;
    this.mediaElement = null;
  }
}

/**
 * AvatarCard — Sprint 53 (housekeeping extraction).
 *
 * Cockpit's avatar slot. Two render modes:
 *   - "sprite": CSSAvatar (88-frame Unicorn sprite, audio-reactive)
 *   - "imgset": ImageSetAvatar (9 PNGs + idle video)
 *
 * Sprint 53 spec originally planned to add a third "live2d" mode
 * backed by `Live2DCanvas` (Cubism pipeline). Per user redirect
 * on 2026-07-02 ("avatar 嘅 sprite sheet + idle video loop 已經係
 * live 2D 效果"), the live2d mode stays as a placeholder — no
 * Live2DCanvas wiring until a real Cubism model lands.
 *
 * Default mode preference: prefers "sprite" (the 88-frame animation
 * has been the cockpit default since Sprint 41). The legacy
 * `localStorage["gundam-halo.avatarMode"] = "image-set"` value
 * is auto-migrated to "imgset" on first render (Sprint 53.3).
 */
import { useCallback, useEffect, useState } from "react";

import { HudCard } from "@/components/gundam/HudCard";
import { CSSAvatar } from "@/components/live2d/CSSAvatar";
import { ImageSetAvatar } from "@/components/live2d/ImageSetAvatar";
import { useHaloLive2D } from "@/context/live2d-bridge-context";

export type AvatarMode = "sprite" | "imgset";

const MODE_ORDER: AvatarMode[] = ["sprite", "imgset"];

const AVATAR_MODE_KEY = "gundam-halo.avatarMode";

/**
 * One-shot migration: legacy "image-set" → "imgset". Without this,
 * a returning user with the old value in localStorage silently
 * resets to "sprite" on first visit (default fallback).
 *
 * Idempotent: writes the new value only when the old value is
 * actually present. Subsequent reads return the migrated value.
 *
 * Returns the effective mode after migration so the caller's
 * initial useState picks up the migrated value (not the legacy
 * "image-set" string the old code would've returned).
 */
function readAndMigrateLegacyMode(): AvatarMode {
  try {
    const raw = localStorage.getItem(AVATAR_MODE_KEY);
    if (raw === "image-set") {
      localStorage.setItem(AVATAR_MODE_KEY, "imgset");
      return "imgset";
    }
    if (raw === "sprite" || raw === "imgset") return raw;
    return "sprite";
  } catch {
    return "sprite";
  }
}

export function AvatarCard() {
  const { state: live2dState } = useHaloLive2D();
  const [mode, setMode] = useState<AvatarMode>(readAndMigrateLegacyMode);

  // Persist mode changes.
  useEffect(() => {
    try {
      localStorage.setItem(AVATAR_MODE_KEY, mode);
    } catch {
      /* localStorage unavailable — non-fatal */
    }
  }, [mode]);

  const handleModeChange = useCallback((next: AvatarMode) => {
    setMode(next);
  }, []);

  const renderAvatar = () => {
    if (mode === "imgset") {
      return (
        <ImageSetAvatar
          emotion={live2dState.lastEmotion ?? undefined}
          enableVideoLoop
        />
      );
    }
    // Default + sprite mode
    return <CSSAvatar emotion={live2dState.lastEmotion ?? undefined} />;
  };

  return (
    <HudCard>
      <div data-testid="avatar-card">
        <div className="flex items-center justify-between mb-2">
          <h2
            className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest"
            data-testid="avatar-card-mode-label"
          >
            RX-0 · {mode === "imgset" ? "IMG" : "SPRITE"}
          </h2>
          {live2dState.lastEmotion && (
            <span className="text-[9px] font-mono text-[var(--accent)] opacity-70">
              EMO: {live2dState.lastEmotion.toUpperCase()}
            </span>
          )}
        </div>
      <div
        className="flex items-center gap-1 mb-2 text-[9px] font-mono"
        data-testid="avatar-card-mode-toggle"
      >
        {MODE_ORDER.map((m) => (
          <button
            key={m}
            type="button"
            data-testid={`avatar-card-mode-${m}`}
            data-active={mode === m ? "true" : "false"}
            onClick={() => handleModeChange(m)}
            aria-pressed={mode === m}
            aria-label={`Avatar mode: ${m === "imgset" ? "image set" : m}`}
            title={
              m === "sprite"
                ? "88-frame sprite sheet, continuous breathing animation"
                : "9 pre-rendered emotion PNGs, instant swap + 6s idle video loop"
            }
            className={`px-2 py-0.5 border rounded uppercase tracking-widest transition-colors ${
              mode === m
                ? "border-[var(--accent)] text-[var(--accent)]"
                : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)]/50"
            }`}
          >
            {m === "imgset" ? "IMG-SET" : m.toUpperCase()}
          </button>
        ))}
      </div>
      <div
        className="w-full rounded overflow-hidden border border-[var(--border-color)]"
        style={{ height: "200px" }}
        data-testid="avatar-card-stage"
      >
        {renderAvatar()}
      </div>
      {live2dState.lastTrigger && (
        <div className="mt-2 space-y-1" data-testid="avatar-card-trigger-state">
          <div className="text-[9px] font-mono text-[var(--text-muted)] truncate">
            EXPR: {live2dState.lastTrigger.expression}
          </div>
          <div className="text-[9px] font-mono text-[var(--text-muted)] truncate">
            MOTION: {live2dState.lastTrigger.motion}
          </div>
        </div>
      )}
      </div>
    </HudCard>
  );
}
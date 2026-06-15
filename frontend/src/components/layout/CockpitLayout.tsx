import { type ReactNode, useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { Toaster } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { Gauge } from "@/components/gundam/Gauge";
import { ConnectionStatus } from "@/components/gundam/ConnectionStatus";
import { MissionLog } from "@/components/gundam/MissionLog";
import { ProjectCard } from "@/components/gundam/ProjectCard";
import { MaybeBackendOutdatedBanner } from "@/components/gundam/BackendOutdatedBanner";
import { SignalCard } from "@/components/gundam/SignalCard";
import { useBackendVersion } from "@/hooks/use-backend-version";
import { useProjectsStore } from "@/stores/projects";
import { useSystemStore } from "@/stores/system";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { useWsEvent, useWsStatus } from "@/lib/ws";
import {
  voiceBegin,
  voiceEnd,
  voiceSendAudio,
} from "@/services/halo-voice-ws";
import { Live2DCanvas } from "@/components/live2d/Live2DCanvas";
import { CSSAvatar } from "@/components/live2d/CSSAvatar";
import { ImageSetAvatar } from "@/components/live2d/ImageSetAvatar";
import { VoicePanel } from "@/components/gundam/VoicePanel";
import { useHaloLive2D } from "@/context/live2d-bridge-context";

type AvatarMode = "sprite" | "image-set";
const AVATAR_MODE_KEY = "gundam-halo.avatarMode";

function useAvatarMode(): [AvatarMode, (m: AvatarMode) => void] {
  const [mode, setMode] = useState<AvatarMode>(() => {
    if (typeof window === "undefined") return "sprite";
    const saved = window.localStorage.getItem(AVATAR_MODE_KEY);
    return saved === "image-set" ? "image-set" : "sprite";
  });
  useEffect(() => {
    if (typeof window === "undefined") return;
    window.localStorage.setItem(AVATAR_MODE_KEY, mode);
  }, [mode]);
  return [mode, setMode];
}

interface CockpitLayoutProps {
  children: ReactNode;
}

type CockpitMode = "select" | "active";

/** Determine cockpit mode from the current route.
 *  select = no project active (Overview, Settings, New)
 *  active = a project page is showing
 */
function useCockpitMode(): { mode: CockpitMode; projectName: string | null } {
  const location = useLocation();
  const match = location.pathname.match(/^\/projects\/([^/]+)(?:\/.*)?$/);
  if (match && match[1] !== "new") {
    return { mode: "active", projectName: match[1] };
  }
  return { mode: "select", projectName: null };
}

/** First-person cockpit layout for desktop (≥768px).
 *
 *  Two modes:
 *    select — Overview / Settings / New. Subdued accent, slow scan,
 *             sidebar shows quick-switch (3 most recent projects).
 *    active — Project page. Brighter accent, faster scan, frame glow,
 *             sidebar shows full project list for navigation.
 *
 *  Frame layers (z-index, bottom → top):
 *   0  background image (optional, [data-bg="core-XX"])
 *   1  hex grid overlay
 *   1  content
 *   5  CRT vignette (fixed, pointer-events: none)
 *   9996 corner brackets + brand/status (fixed)
 *   9997 top scan line (fixed)
 */
export function CockpitLayout({ children }: CockpitLayoutProps) {
  const { projects, fetchProjects } = useProjectsStore();
  const { gauges, setGauges, startPolling } = useSystemStore();
  const { connected } = useWsStatus();
  const { mode, projectName } = useCockpitMode();
  const location = useLocation();
  const { state: live2dState } = useHaloLive2D();
  const [avatarMode, setAvatarMode] = useAvatarMode();
  const { backend, outdated, missingFeatures } = useBackendVersion();

  // Sprint 18 Track A: hoist the mic hook to the cockpit so the
  // right column can render an audio-reactive CyberWaveform *and*
  // VoicePanel can share the same stream + state. CyberWaveform
  // subscribes to `mic.stream` + a "mic"/"idle" source flag derived
  // from `mic.state === "capturing"`. VoicePanel receives the same
  // `mic` object as a prop and uses it for the push-to-talk button.
  // The voice WS turn lifecycle (voiceBegin / voiceEnd / voiceSendAudio)
  // is co-located with the mic lifecycle here, mirroring what
  // VoicePanel used to do in Sprint 17a/17b.
  const mic = useVoiceInput({
    onFrame: voiceSendAudio,
    onStart: () => {
      try {
        voiceBegin();
      } catch (e) {
        // non-fatal: mic captures audio even if WS turn-open fails;
        // VoicePanel surfaces its own toast on the next send.
        console.warn("[CockpitLayout] voiceBegin failed:", e);
      }
    },
    onStop: () => {
      try {
        voiceEnd();
      } catch (e) {
        console.warn("[CockpitLayout] voiceEnd failed:", e);
      }
    },
  });

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Push live gauges from WS into the store.
  useWsEvent("system_gauges", (event) => {
    setGauges(event.data);
  });

  // Fallback to REST polling if WS isn't connected (e.g. server restart).
  useEffect(() => {
    if (connected) return; // WS will handle it
    const stop = startPolling();
    return stop;
  }, [connected, startPolling]);

  // Sidebar content depends on mode
  const recentMissions = projects.slice(0, 3);

  return (
    <div className={`gundam-cockpit-frame gundam-cockpit-vignette gundam-hex-bg gundam-mode-${mode} min-h-screen flex flex-col`}>
      {/* Background image layer (visible only when [data-bg] is set on <html>) */}
      <div className="gundam-cockpit-bg" aria-hidden="true" />

      {/* Toaster (Sonner) — global */}
      <Toaster
        theme="dark"
        position="top-right"
        richColors
        toastOptions={{
          classNames: {
            toast:
              "!bg-[var(--bg-card)] !border !border-[var(--accent)] !text-[var(--text-primary)]",
            title: "!text-[var(--accent)] !font-[Orbitron] !tracking-wider",
            description: "!text-[var(--text-secondary)]",
          },
        }}
      />

      {/* Frame chrome (fixed) — corner brackets, brand, status */}
      <div className="gundam-frame-corner gundam-frame-corner-tl" aria-hidden="true" />
      <div className="gundam-frame-corner gundam-frame-corner-tr" aria-hidden="true" />
      <div className="gundam-frame-corner gundam-frame-corner-bl" aria-hidden="true" />
      <div className="gundam-frame-corner gundam-frame-corner-br" aria-hidden="true" />
      <div className="gundam-frame-brand" aria-hidden="true">
        {mode === "active" && projectName
          ? `GUNDAM HALO // MISSION: ${projectName}`
          : "GUNDAM HALO // AWAITING ORDERS"}
      </div>
      <div className="gundam-frame-status" aria-hidden="true">
        {mode === "active" ? "MISSION ACTIVE" : "STANDBY"} · v{APP_VERSION}
      </div>
      <div className="gundam-scan" aria-hidden="true" />

      {/* Backend-outdated banner — only renders when git SHA mismatches
          or required features are missing. Polled every 30s. */}
      <MaybeBackendOutdatedBanner
        outdated={outdated}
        backend={backend}
        missingFeatures={missingFeatures}
      />

      {/* Top bar — project nav. Responsive padding for chrome. */}
      <header className="border-b border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 md:pl-48 md:pr-44 py-3 mt-2 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <h1 className="text-xl font-[Orbitron] text-[var(--accent)] tracking-widest uppercase">
            Gundam Halo
          </h1>
          <span className="text-xs text-[var(--text-muted)] font-mono hidden sm:inline">
            {mode === "active" && projectName
              ? `// MISSION: ${projectName}`
              : "// COCKPIT"}
          </span>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          <Link
            to="/"
            className={`px-2 py-1 hover:text-[var(--accent)] ${
              location.pathname === "/" ? "text-[var(--accent)]" : "text-[var(--text-secondary)]"
            }`}
          >
            Overview
          </Link>
          <Link
            to="/projects/new"
            className="px-2 py-1 hover:text-[var(--accent)] text-[var(--text-secondary)]"
          >
            + New
          </Link>
          <Link
            to="/settings"
            className={`px-2 py-1 hover:text-[var(--accent)] ${
              location.pathname === "/settings" ? "text-[var(--accent)]" : "text-[var(--text-secondary)]"
            }`}
          >
            Settings
          </Link>
        </nav>
      </header>

      <div className="flex-1 grid grid-cols-1 md:grid-cols-[200px_1fr_240px] gap-3 p-3 min-h-0">
        {/* Left panel — adaptive by mode:
            - select mode: Quick Switch (3 most recent + New)
            - active mode: Full Projects list + Mission Log */}
        <aside className="overflow-y-auto space-y-3">
          {mode === "select" ? (
            <HudCard>
              <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
                Quick Switch
              </h2>
              <div className="space-y-2">
                {recentMissions.length === 0 ? (
                  <div className="text-[var(--text-muted)] text-xs text-center py-3">
                    No projects yet
                  </div>
                ) : (
                  recentMissions.map((p) => (
                    <ProjectCard key={p.name} project={p} />
                  ))
                )}
                <Link
                  to="/projects/new"
                  className="block text-center text-[10px] font-[Rajdhani] uppercase tracking-widest py-2 border border-dashed border-[var(--border-color)] text-[var(--text-muted)] rounded hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
                >
                  + Initialize New
                </Link>
              </div>
            </HudCard>
          ) : (
            <>
              <HudCard>
                <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
                  Projects
                </h2>
                <div className="space-y-2">
                  {projects.length === 0 && (
                    <div className="text-[var(--text-muted)] text-xs text-center py-3">
                      No projects yet
                    </div>
                  )}
                  {projects.map((p) => (
                    <ProjectCard key={p.name} project={p} />
                  ))}
                </div>
              </HudCard>

              <HudCard>
                <div className="flex items-center justify-between mb-2">
                  <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                    Mission Log
                  </h2>
                  <span className="text-[9px] text-[var(--text-muted)] font-mono">
                    LIVE FEED
                  </span>
                </div>
                <MissionLog maxEntries={30} />
              </HudCard>
            </>
          )}
        </aside>

        {/* Center — main content */}
        <main className="overflow-y-auto min-w-0">{children}</main>

        {/* Right panel — CSS Avatar + Mac system gauges */}
        <aside className="overflow-y-auto space-y-3">
          {/* Sprint 18 Track A: audio-reactive CyberWaveform above
              the avatar. Source flips to "mic" while the user holds
              the push-to-talk button (mic.state === "capturing"),
              otherwise idle drift. 80px is a compact cockpit width;
              the dev /cyber-wave-demo route still shows the full
              160px form. The SignalCard component encapsulates
              this logic and is unit-tested in SignalCard.test.tsx. */}
          <HudCard>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                Signal
              </h2>
              <span className="text-[9px] font-mono text-[var(--text-muted)]">
                {mic.state === "capturing" ? "● LIVE" : "○ IDLE"}
              </span>
            </div>
            <SignalCard mic={mic} />
          </HudCard>

          <HudCard>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
                Avatar
              </h2>
              {live2dState.lastEmotion && (
                <span className="text-[9px] font-mono text-[var(--accent)] opacity-70">
                  EMO: {live2dState.lastEmotion.toUpperCase()}
                </span>
              )}
            </div>
            {/* Mode toggle — sprite (88-frame animation) vs image-set (9 PNGs + idle video) */}
            <div className="flex items-center gap-1 mb-2 text-[9px] font-mono">
              <button
                type="button"
                onClick={() => setAvatarMode("sprite")}
                className={`px-2 py-0.5 border rounded uppercase tracking-widest transition-colors ${
                  avatarMode === "sprite"
                    ? "border-[var(--accent)] text-[var(--accent)]"
                    : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)]/50"
                }`}
                title="88-frame sprite sheet, continuous breathing animation"
              >
                SPRITE
              </button>
              <button
                type="button"
                onClick={() => setAvatarMode("image-set")}
                className={`px-2 py-0.5 border rounded uppercase tracking-widest transition-colors ${
                  avatarMode === "image-set"
                    ? "border-[var(--accent)] text-[var(--accent)]"
                    : "border-[var(--border-color)] text-[var(--text-muted)] hover:border-[var(--accent)]/50"
                }`}
                title="9 pre-rendered emotion PNGs, instant swap + 6s idle video loop"
              >
                IMG-SET
              </button>
            </div>
            {/* CSS Avatar — auto-responds to live2d.trigger WS events */}
            <div
              className="w-full rounded overflow-hidden border border-[var(--border-color)]"
              style={{ height: "200px" }}
            >
              {avatarMode === "sprite" ? (
                <CSSAvatar emotion={live2dState.lastEmotion ?? undefined} />
              ) : (
                <ImageSetAvatar
                  emotion={live2dState.lastEmotion ?? undefined}
                  enableVideoLoop
                />
              )}
            </div>
            {/* Show live2d trigger state */}
            {live2dState.lastTrigger && (
              <div className="mt-2 space-y-1">
                <div className="text-[9px] font-mono text-[var(--text-muted)] truncate">
                  EXPR: {live2dState.lastTrigger.expression}
                </div>
                <div className="text-[9px] font-mono text-[var(--text-muted)] truncate">
                  MOTION: {live2dState.lastTrigger.motion}
                </div>
              </div>
            )}
          </HudCard>

          <HudCard>
            <VoicePanel mic={mic} />
          </HudCard>

          <HudCard>
            <h2 className="text-xs font-[Orbitron] text-[var(--accent)] uppercase tracking-widest mb-3">
              System
            </h2>
            <div className="flex justify-around items-end h-32">
              <Gauge label="CPU" value={gauges?.cpu_percent ?? 0} />
              <Gauge label="RAM" value={gauges?.memory_percent ?? 0} />
              <Gauge label="DSK" value={gauges?.disk_percent ?? 0} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-1 text-[10px] font-mono text-[var(--text-muted)]">
              <div>↑ {(gauges?.network_sent_mb ?? 0).toFixed(1)} MB</div>
              <div>↓ {(gauges?.network_recv_mb ?? 0).toFixed(1)} MB</div>
            </div>
            <div className="mt-2 pt-2 border-t border-[var(--border-color)]">
              <ConnectionStatus />
            </div>
          </HudCard>
        </aside>
      </div>

      {/* Bottom bar — status */}
      <footer className="border-t border-[var(--border-color)] bg-[var(--bg-card)]/80 backdrop-blur-md px-4 py-2 mb-2 mx-2 text-xs text-[var(--text-muted)] font-mono flex items-center justify-between gap-4">
        <span>RX-0 // UNICORN</span>
        <span className="shrink-0">{location.pathname}</span>
      </footer>
    </div>
  );
}

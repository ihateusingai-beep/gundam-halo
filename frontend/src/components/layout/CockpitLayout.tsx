import { type ReactNode, useEffect, useState } from "react";
import { Link, useLocation } from "react-router";
import { Toaster } from "sonner";

import { HudCard } from "@/components/gundam/HudCard";
import { resolveBgAsset } from "@/routes/settings/constants";
import { useThemeStore } from "@/stores/theme";
import { Gauge } from "@/components/gundam/Gauge";
import { ConnectionStatus } from "@/components/gundam/ConnectionStatus";
import { MissionLog } from "@/components/gundam/MissionLog";
import { ProjectCard } from "@/components/gundam/ProjectCard";
import { MaybeBackendOutdatedBanner } from "@/components/gundam/BackendOutdatedBanner";
import { BackendHealthBanner } from "@/components/gundam/BackendHealthBanner";
import { RestartNudgeBanner } from "@/components/gundam/RestartNudgeBanner";
import { SignalCard } from "@/components/gundam/SignalCard";
import { CockpitEqCard } from "@/components/gundam/CockpitEqCard";
import { AvatarCard } from "@/components/live2d/AvatarCard";
import { useBackendVersion } from "@/hooks/use-backend-version";
import { useProjectsStore } from "@/stores/projects";
import { useSystemStore } from "@/stores/system";
import { useVoiceInput } from "@/hooks/use-voice-input";
import { useVadStateAutoFire } from "@/hooks/use-vad-state-autofire";
import { useWsEvent, useWsStatus } from "@/lib/ws";
import { api } from "@/lib/api";
import { useBackendHealth } from "@/lib/use-backend-health";
import { getVoiceStatus, onVoiceStatusChange } from "@/services/halo-voice-ws";
import { Breadcrumb } from "./Breadcrumb";
import { OfflineBanner } from "./OfflineBanner";
import { RAIL_KEY, RailToggle } from "./RailToggle";
import {
  voiceBegin,
  voiceEnd,
  voiceSendAudio,
} from "@/services/halo-voice-ws";
import { VoicePanel } from "@/components/gundam/VoicePanel";

interface CockpitLayoutProps {
  children: ReactNode;
}

type CockpitMode = "select" | "active";

/** Hook — derive the cockpit's visual mode from the current URL.
 *
 *  Inputs:
 *    - `useLocation()` (react-router) — reads `pathname` reactively.
 *
 *  Returns `{ mode, projectName }`:
 *    - `mode = "active"` only when the path matches `/projects/<name>`
 *      (or `/projects/<name>/...`) AND `<name>` is NOT the literal
 *      `"new"`. The `/projects/new` route is the creation form, not
 *      an active mission, so it stays in `select` mode.
 *    - `mode = "select"` for everything else (overview, settings,
 *      audit, setup).
 *    - `projectName` is the URL slug in active mode, null in select.
 *
 *  Used by:
 *    - The `CockpitLayout` component to switch the 3-column sidebar
 *      (Quick Switch vs. Projects list), the top-bar subtitle, and
 *      the frame-corner brand text (`// MISSION: <name>` vs.
 *      `// AWAITING ORDERS`).
 *
 *  Note: a regex match is intentional (vs. router params) because
 *  `CockpitLayout` is a route-blanket shell that mounts on every
 *  page — pulling `useParams()` would require every child route to
 *  expose the slug, which they already do via `useLocation()`.
 */
function useCockpitMode(): { mode: CockpitMode; projectName: string | null } {
  const location = useLocation();
  const match = location.pathname.match(/^\/projects\/([^/]+)(?:\/.*)?$/);
  if (match && match[1] !== "new") {
    return { mode: "active", projectName: match[1] };
  }
  return { mode: "select", projectName: null };
}

/** Top-level layout component for the desktop cockpit (≥768px).
 *
 *  Renders the full cockpit shell around `children`:
 *    - Frame chrome (corner brackets, brand banner, status, scan line)
 *    - 3-column grid: left sidebar (project switcher / mission log),
 *      center content (`children`), right rail (signal/avatar/voice/EQ/system)
 *    - Top header with persistent breadcrumb (Sprint 49 #6)
 *    - Footer with current path
 *    - Global Sonner toaster (top-right, themed)
 *    - Background health banners (Backend watchdog, offline,
 *      restart-nudge, backend-outdated)
 *
 *  Props:
 *    - `children` — the route-specific content (rendered in the
 *      center column).
 *
 *  Side-effects on mount:
 *    - Fetches voice config (`always_on_mic`) — re-fetches on
 *      visibility change / window focus.
 *    - Subscribes to WS `system_gauges` event.
 *    - Starts REST polling fallback for system gauges when WS
 *      is disconnected.
 *    - Boots the voice input stream (push-to-talk or always-on).
 *    - Subscribes to VAD auto-fire for always-on mode.
 *
 *  Reads from stores:
 *    - `useProjectsStore` — projects list (for sidebar / mission log).
 *    - `useSystemStore` — gauges (CPU/RAM/DSK + network counters).
 *    - `useThemeStore` — theme + background slug (Sprint 58: for
 *      the inline cockpit-bg `backgroundImage`).
 *    - `useBackendVersion` — git SHA + feature compatibility check.
 *    - `useBackendHealth` — Sprint 49 B3 3-state machine
 *      (loading / online / offline).
 *    - `getVoiceStatus()` + `onVoiceStatusChange()` — for the
 *      `live` flag passed to `CockpitEqCard`.
 *
 *  Two modes (via `useCockpitMode()`):
 *    select — Overview / Settings / New. Subdued accent, slow scan,
 *             sidebar shows quick-switch (3 most recent projects).
 *    active — Project page. Brighter accent, faster scan, frame glow,
 *             sidebar shows full project list + mission log.
 *
 *  Frame layers (z-index, bottom → top):
 *    0  background image (optional, [data-bg="core-XX"])
 *    1  hex grid overlay
 *    1  content
 *    5  CRT vignette (fixed, pointer-events: none)
 *    9996 corner brackets + brand/status (fixed)
 *    9997 top scan line (fixed)
 */
export function CockpitLayout({ children }: CockpitLayoutProps) {
  const { projects, fetchProjects } = useProjectsStore();
  const { gauges, setGauges, startPolling } = useSystemStore();
  const { connected } = useWsStatus();
  const { mode, projectName } = useCockpitMode();
  const location = useLocation();
  const { backend, outdated, missingFeatures } = useBackendVersion();

  // Sprint 19c: read the always_on_mic config so the
  // cockpit can auto-fire the agent on VAD events when
  // the user has enabled always-on mode. The default
  // is false (push-to-talk) so the existing Sprint 16
  // / 17a / 17b / 18 behavior is preserved.
  const [alwaysOnMic, setAlwaysOnMic] = useState<boolean>(false);
  // Pause state — flips from ⏸ toggle in VoicePanel.
  // When true, useVadStateAutoFire ignores VAD events.
  const [micPaused, setMicPaused] = useState<boolean>(false);

  // Sprint 49 B3: 3-state health machine. The cockpit shell
  // renders immediately; content + offline banner reflect
  // the health state. Per-card skeletons handle their own
  // loading — this hook only governs the top-level shell.
  const health = useBackendHealth();

  // Sprint 57: subscribe to voice status so the EQ visualizer
  // lights up when the agent is speaking. VoicePanel also
  // subscribes (independently) for its own state; this is
  // a one-way fire-and-forget.
  const [voiceStatus, setVoiceStatusState] = useState(() => getVoiceStatus());
  useEffect(() => onVoiceStatusChange(setVoiceStatusState), []);

  // Sprint 49 #5: right-rail collapse. Default collapsed
  // (the rail is empty/zero state when healthy) so the
  // center content has more room. Persist the user's
  // preference to localStorage so it survives reload.
  // Schema-versioned to make future migrations safer.
  // The RAIL_KEY is shared with RailToggle (imported) so
  // the two components read/write the same slot.
  const [railExpanded, setRailExpanded] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    try {
      return window.localStorage.getItem(RAIL_KEY) === "1";
    } catch {
      return false;
    }
  });

  // Sprint 58: per-theme cockpit background. Subscribe to the
  // store so we re-derive the asset URL whenever the user picks
  // a new theme (the store's setTheme cascade switches the
  // slug, but the actual asset URL also depends on the theme).
  const theme = useThemeStore((s) => s.theme);
  const background = useThemeStore((s) => s.background);
  const cockpitBgUrl = background !== "none" ? resolveBgAsset(background, theme) : null;
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(RAIL_KEY, railExpanded ? "1" : "0");
    } catch {
      /* localStorage disabled (private mode) — silently ignore */
    }
  }, [railExpanded]);

  // Fetch the voice config on mount and on Settings save.
  // We don't subscribe to a store here; the simplest
  // correct thing is to re-fetch on mount and on the
  // page-visibility change. The user typically
  // toggles always-on from the Settings tab; when they
  // return to the cockpit, the new value will be
  // applied via this effect's cleanup + remount.
  useEffect(() => {
    let alive = true;
    /** Fire-and-forget: GET /api/voice/config, update
     *  `alwaysOnMic` state if the response carries a
     *  defined `always_on_mic` field. The `alive` guard
     *  prevents state writes after unmount (the effect
     *  cleanup flips it false). Failures are silent —
     *  the cockpit falls back to push-to-talk (default
     *  `false`) if the backend is unreachable. */
    const fetchCfg = () => {
      api
        .getVoiceConfig()
        .then((d) => {
          if (alive && d.always_on_mic !== undefined) {
            setAlwaysOnMic(d.always_on_mic);
          }
        })
        .catch(() => {
          /* non-fatal — fall back to the default false */
        });
    };
    fetchCfg();
    /** Visibility handler — refetch when the tab
     *  returns to the foreground (handles the case
     *  where the user toggled always-on in the Settings
     *  tab, then switched back to the cockpit tab). */
    const onVis = () => {
      if (document.visibilityState === "visible") fetchCfg();
    };
    document.addEventListener("visibilitychange", onVis);
    window.addEventListener("focus", fetchCfg);
    return () => {
      alive = false;
      document.removeEventListener("visibilitychange", onVis);
      window.removeEventListener("focus", fetchCfg);
    };
  }, []);

  // Sprint 18 Track A: hoist the mic hook to the cockpit so the
  // right column can render an audio-reactive CyberWaveform *and*
  // VoicePanel can share the same stream + state. CyberWaveform
  // subscribes to `mic.stream` + a "mic"/"idle" source flag derived
  // from `mic.state === "capturing"`. VoicePanel receives the same
  // `mic` object as a prop and uses it for the push-to-talk button.
  // The voice WS turn lifecycle (voiceBegin / voiceEnd / voiceSendAudio)
  // is co-located with the mic lifecycle here, mirroring what
  // VoicePanel used to do in Sprint 17a/17b.
  //
  // Sprint 19c: when `alwaysOn` is true, the hook auto-starts
  // the mic on mount and keeps it open across turns. The
  // onStart / onStop callbacks are no longer tied to the
  // press-and-hold button; they're driven by the
  // useVadStateAutoFire listener below.
  const mic = useVoiceInput({
    alwaysOn: alwaysOnMic,
    onFrame: voiceSendAudio,
    /** `useVoiceInput` callback — fires when the mic capture
     *  stream transitions from idle to capturing.
     *
     *  Behaviour by mode:
     *    - always-on (alwaysOnMic=true): no-op. The WS turn
     *      is opened by `useVadStateAutoFire` on `speech_start`,
     *      not by the mic stream lifecycle. Opening it here
     *      would create a phantom empty turn.
     *    - push-to-talk (alwaysOnMic=false): opens a WS turn
     *      via `voiceBegin()` so the next `voiceSendAudio()`
     *      frame has a server-side receiver. Failures are
     *      non-fatal (the mic still captures audio; VoicePanel
     *      surfaces its own toast on the next failed send). */
    onStart: () => {
      // No-op in always-on mode (the WS turn is opened
      // by useVadStateAutoFire on speech_start). In
      // push-to-talk mode this still fires on the
      // press-and-hold gesture and opens the WS turn.
      if (alwaysOnMic) return;
      try {
        voiceBegin();
      } catch (e) {
        // non-fatal: mic captures audio even if WS turn-open fails;
        // VoicePanel surfaces its own toast on the next send.
        console.warn("[CockpitLayout] voiceBegin failed:", e);
      }
    },
    /** `useVoiceInput` callback — fires when the mic capture
     *  stream transitions from capturing to idle.
     *
     *  Behaviour by mode:
     *    - always-on (alwaysOnMic=true): no-op. The WS turn
     *      is closed by `useVadStateAutoFire` on `speech_end`.
     *    - push-to-talk: closes the WS turn via `voiceEnd()`
     *      so the server-side pipeline finalises and the
     *      transcript can stream back. Failures are logged
     *      but don't block the user. */
    onStop: () => {
      // No-op in always-on mode (the WS turn is closed
      // by useVadStateAutoFire on speech_end).
      if (alwaysOnMic) return;
      try {
        voiceEnd();
      } catch (e) {
        console.warn("[CockpitLayout] voiceEnd failed:", e);
      }
    },
  });

  // Sprint 19c: when always-on mode is enabled, subscribe
  // to the backend's vad.state events and auto-fire the
  // WS turn. The pause flag lets the user mute the mic
  // (e.g. during a phone call) without toggling always-on
  // off entirely.
  useVadStateAutoFire({ enabled: alwaysOnMic, paused: micPaused });

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Push live gauges from WS into the store.
  /** WS event handler — receives a `system_gauges` payload
   *  (CPU %, RAM %, DSK %, network sent/recv MB) and writes
   *  it into the system store. The store is the source of
   *  truth for the gauge components in the right rail.
   *  Frequency: backend pushes roughly every 2s. */
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
      {/* Background image layer (Sprint 58: per-theme asset URL
          computed inline from the current theme + bg slug; falls
          back to no image when bg = "none"). The CSS rule on
          `.gundam-cockpit-bg` only sets the safety-net
          background-image: none, so the inline style here is what
          actually paints the wallpaper. */}
      <div
        className="gundam-cockpit-bg"
        aria-hidden="true"
        style={
          cockpitBgUrl
            ? { backgroundImage: `url(${cockpitBgUrl})` }
            : undefined
        }
      />

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

      {/* Backend-health banner — Sprint 43. Renders when the Tauri
          watchdog detects the backend is unreachable (yellow) or has
          crashed 3+ times in the last hour (red, with action buttons
          to clear the crash log + install the launchd supervisor).
          Hidden by default when the backend is healthy. */}
      <BackendHealthBanner />

      {/* Sprint 49 B3: 3-state health machine. Renders the
          OfflineBanner when the initial health check fails. The
          watchdog banner above handles Tauri-side runtime crashes;
          this one handles the first-load / proxy-down case. */}
      <OfflineBanner state={health} />

      {/* Sprint 41 — restart nudge banner. Renders when the
          backend has a self-restart scheduled (5-second
          countdown after an asr_backend / asr_corrector
          change). Hidden by default. */}
      <RestartNudgeBanner />

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
          {/* Sprint 49 #6: persistent breadcrumb. Derived from
              useLocation; hidden on `/` (home is implicit). Renders
              inside the header so it shows on every page without
              per-route wiring. */}
          <div className="hidden md:block">
            <Breadcrumb />
          </div>
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

      <div
        className={`flex-1 grid grid-cols-1 gap-3 p-3 min-h-0 ${
          railExpanded
            ? "md:grid-cols-[200px_1fr_240px]"
            : "md:grid-cols-[200px_1fr_48px]"
        }`}
        data-testid="cockpit-3col"
        data-rail-expanded={railExpanded ? "1" : "0"}
      >
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

        {/* Right panel — CSS Avatar + Mac system gauges.
            Sprint 49 #5: collapsed by default (just a vertical
            tab strip with a toggle). Click the tab to expand.
            State persists in localStorage. The 48 px collapsed
            width fits the expand-tab + a "···" indicator. */}
        <aside
          className="overflow-y-auto space-y-3"
          data-testid="cockpit-right-rail"
          data-expanded={railExpanded ? "1" : "0"}
        >
          {/* Always-visible tab strip — single button that
              toggles the rail. State persisted to localStorage.
              See ./RailToggle.tsx for the standalone component
              (tested in CockpitLayout.test.tsx). */}
          <RailToggle />
          {railExpanded && (
            <>
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

              <AvatarCard />

              <HudCard>
                <VoicePanel
                  mic={mic}
                  alwaysOn={alwaysOnMic}
                  paused={micPaused}
                  onPausedChange={setMicPaused}
                />
              </HudCard>

              {/* Sprint 57: per-theme TTS equalizer visualizer.
                  Owns a SEPARATE TtsAudioGraph (read-only — never
                  connects to an audio source) for visualizing
                  the active EQ profile. The active playback
                  chain lives in VoicePanel; the visualizer just
                  reads the preset + filter state for display. */}
              <CockpitEqCard
                live={mic.state === "capturing" || voiceStatus.state === "speaking"}
              />

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
            </>
          )}
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

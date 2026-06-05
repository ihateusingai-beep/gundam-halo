# Gundam Halo — Frontend

Cockpit-themed web UI built with **Vite + React 19 + shadcn/ui + Tailwind v4 + Tauri 2**.

**Status**: 🚧 Scaffold (Day 1). Architecture spec: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Dashboard spec: [`../docs/DASHBOARD.md`](../docs/DASHBOARD.md).

## Quick start (web dev)

```bash
# Install
npm install

# Make sure backend is running on :8765 (see ../backend/README.md)

# Run
npm run dev
# Open http://localhost:5173
```

## Quick start (Tauri desktop)

```bash
# One-time: install Tauri CLI prerequisites (Rust toolchain, etc.)
# See: https://tauri.app/start/prerequisites/

# Install
npm install

# Run Tauri dev (compiles + runs the desktop app)
npm run tauri dev
```

## Module layout

```
src/
├── main.tsx              # Entry, sets default data-theme
├── App.tsx               # Router + layout switcher
├── routes/               # React Router 7
│   ├── index.tsx         # Cockpit overview
│   ├── projects/[id].tsx # Project detail (chat)
│   └── settings.tsx
├── components/
│   ├── gundam/           # Cockpit-specific
│   │   ├── HudCard.tsx
│   │   ├── Radar.tsx
│   │   ├── Gauge.tsx
│   │   ├── RingProgress.tsx
│   │   ├── Reticle.tsx
│   │   ├── HoloPanel.tsx
│   │   ├── StatusDot.tsx
│   │   ├── EnergyBar.tsx
│   │   ├── ThemeSwitcher.tsx
│   │   └── CommandInput.tsx
│   └── layout/
│       ├── CockpitLayout.tsx    # Desktop (≥768px) first-person grid
│       └── MobileLayout.tsx     # Mobile (<768px) vertical stack
├── stores/               # Zustand
│   ├── theme.ts
│   ├── projects.ts
│   └── system.ts
├── lib/
│   ├── api.ts            # FastAPI client
│   ├── ws.ts             # WebSocket client
│   ├── utils.ts
│   └── use-responsive.ts
├── types/
│   └── api.ts            # Mirrors backend Pydantic models
└── styles/
    └── gundam.css        # Gundam Console UI CSS (8 themes, 12 keyframes)
```

## Theme system

Default: `gundam-ntd` (NT-D / Unicorn). 8 switchable themes via the floating switcher button (bottom-right) or `/settings`.

Theme is stored in `localStorage` under `gundam-halo-theme`. Set on `<html>` `data-theme` attribute.

See [`../docs/DASHBOARD.md`](../docs/DASHBOARD.md) §2 for the full theme system spec.

## Backend connection

By default, the frontend talks to `http://localhost:8765`. Override with the `VITE_API_BASE` env var.

```bash
# Tailscale
VITE_API_BASE=https://gundam-halo.tail-net.ts.net npm run dev

# Custom port
VITE_API_BASE=http://localhost:9999 npm run dev
```

## Tauri 2 features

- ✅ Single window
- ✅ Menu bar tray icon (click to focus, right-click menu)
- ✅ Window state persistence
- ✅ Autostart on login (launch agent, then minimized)
- ⏸ Global hotkey (configurable in `~/.gundam-halo/config.toml`) — needs to be wired up
- ❌ Floating panel — v2 if needed

See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md) §6.7 for desktop strategy.

## License

MIT — see [`../LICENSE`](../LICENSE).

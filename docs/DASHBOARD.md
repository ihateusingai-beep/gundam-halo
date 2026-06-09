# Gundam Halo — Dashboard Design

> **Cockpit-themed dashboard** for personal AI agent on Mac. Built on the [gundam-design](../../gundam-design/) skill system.

**Status**: 📐 Design spec — locks the visual language, layout, and component choices. Implementation will follow.

---

## 1. Why a cockpit dashboard?

The gundam-design skill's core philosophy is **第一人稱沉浸 (first-person immersion)** — the user is the pilot, the dashboard is the cockpit, every panel is a system readout. This maps cleanly to Gundam Halo's needs:

- **Per-project isolation** = each project = a separate "mobile suit" with its own status panel
- **Mac control** = cockpit gauges (CPU, RAM, disk, network)
- **Real-time activity** = radar / reticle / status pulses
- **Remote control via phone** = the same view works on small screens (cockpit layouts are responsive by design)

The 3 core design principles from the skill carry over verbatim:

1. **軍事精準** (military precision) — every readout has a clear meaning, no decorative noise
2. **第一人稱沉浸** (first-person immersion) — you're piloting, not browsing
3. **高對比黑暗中清晰** (clarity in darkness) — default dark theme, NT-D cyan + psychoframe pink as primary signal colors

---

## 2. Theme system

### Default theme: **NT-D / Unicorn** (`gundam-ntd`)

Per user decision (2026-06-04). Accent: `#00D4FF` (cyan) + `#FF69B4` (psychoframe pink). Most iconic of the 8 available themes.

### 8 switchable themes (via the skill's switcher widget)

| Attribute | Name | Primary | Signature |
|---|---|---|---|
| `gundam-ntd` | **NT-D / Unicorn** ⭐ default | `#00D4FF` | Psychoframe pink pulse |
| `gundam-seed` | SEED Freedom | `#FFD700` | Prismatic burst |
| `gundam-crossbone` | Crossbone X-1 | `#CC0000` | Skull flash |
| `gundam-ntd-green` | NT-D Green Frame | `#00FF88` | Scan wave +感应波 |
| `gundam-00` | 00 Qubit | `#00FF88` | Trans-Am burst |
| `gundam-destiny` | Destiny / Legend | `#CC0000` | Beam blade shimmer |
| `gundam-god` | God Gundam | `#FF6600` | Flame surge |
| `gundam-cartoon` | Cartoon Kawaii | `#FF9ECF` | Bounce + wobble |

### Theme application rules (from skill, mandatory)

- **Theme via `data-theme` attribute on `<html>` ONLY**. Do not try to inject classes onto React-managed elements via `querySelectorAll` after the bundle loads — React owns the DOM, class additions get overwritten on re-render.
- Use **CSS attribute selectors**: `[data-theme^="gundam-"] .gundam-hud-card { ... }`
- React integration via `useEffect`:
  ```tsx
  const [theme, setTheme] = useState<GundamTheme>('gundam-ntd');
  useEffect(() => {
    document.documentElement.removeAttribute('data-theme');
    if (theme) document.documentElement.setAttribute('data-theme', theme);
  }, [theme]);
  ```
- All animations respect `prefers-reduced-motion: reduce` (skill provides the media query).
- Light-mode fallback for non-cartoon themes is provided in the skill.

### Theme switcher widget

The skill provides a complete fixed-position switcher (bottom-right, 72×72px button, expanding to 8 mode buttons + OFF). Use it as-is from `SKILL.md` lines 1437-1475. It's vanilla JS + inline CSS, works alongside any React app.

### Per-user theme storage

- Default: `gundam-ntd`
- User override: persisted in `~/.gundam-halo/config.toml` under `[ui] theme = "gundam-ntd"`
- Read at app boot, applied via the React useEffect pattern above.
- **No per-project theme override** in v1 (one theme at a time keeps the system simple). Reconsider in v2 if it becomes a real pain point.

---

## 3. Dashboard layout — first-person cockpit

The skill's canonical first-person view:

```
        ┌──────────────────────────────────┐
[導航]  │           中央焦點區             │  [雷達]
        │     瞄準 / 目標鎖定 / 速度         │
[狀態]  │        (最大、最亮)              │  [能源]
        │                                   │
[通信]  │    周邊狀態欄 (中等大小)         │  [系統]
        │                                   │
        │    浮動全息窗口 (可折疊)           │
        └──────────────────────────────────┘
        底部威脅指示 / 快速狀態 (最小)
```

### Mapped to Gundam Halo

| Cockpit region | Gundam Halo element | Component | Priority |
|---|---|---|---|
| **Top-left (導航)** | Project switcher (active + recent) | `.gundam-hud-card` + status indicators | Medium |
| **Top-right (雷達)** | Active project activity radar | `.gundam-radar` (60-80px) | High (small but visible) |
| **Center (焦點)** | Active project chat / agent output | `.gundam-reticle` wrapper + chat content | **Largest, brightest, primary** |
| **Middle-left (狀態)** | Skills/tools registry status | `.gundam-status-ok/warn/alert` list | Medium |
| **Middle-right (能源)** | Mac system gauges (CPU / RAM / disk / network) | `.gundam-gauge-v` × 4 | Medium |
| **Bottom-left (通信)** | Incoming channels (Telegram / Signal feeds) | `.gundam-holo-panel` | Low-medium |
| **Bottom-right (系統)** | Theme switcher (skill-provided widget) | skill switcher | N/A |
| **Bottom (威脅)** | Audit log / recent actions / security alerts | `.gundam-data-stream` | Lowest (small) |

### Information priority rules (from skill)

| Priority | Size | Brightness | Color | Animation |
|---|---|---|---|---|
| 緊急 (security alert / error) | Large | Brightest | Danger red | `damageFlash` + `screenShake` |
| 重要 (active agent / project) | Large | Highlighted | Accent cyan | `targetLock` sweep |
| 正常 (system status) | Medium | Medium | Accent | `slowPulse` |
| 背景 (decoration / nav) | Small | Dim | Muted | None / `scanline` only |

**Reading rule**: in any ambiguous layout decision, the closer to center and the bigger the element, the more important it is. **The active project's chat always wins for attention.**

### 3.5 Responsive / mobile behavior (locked 2026-06-05)

Cockpit layouts are grid-based and don't shrink well. **Strategy: responsive cockpit + Telegram/Signal as the primary mobile control surface.**

**Breakpoints**:
- `≥1280px` (desktop) — full cockpit grid as designed
- `768–1279px` (tablet) — same layout, slightly tighter spacing, gauges shrink
- `<768px` (phone) — vertical stack, with collapsible sections

**Phone layout** (vertical top-to-bottom):
1. Project switcher (full-width pill, tap to expand list)
2. Active project chat (full-width, large, primary focus)
3. Gauges — **single horizontal bar** showing CPU / RAM / disk as a stacked segmented bar (not 4 vertical gauges)
4. **Collapsed sections** (3 tabs at bottom):
   - **System** — gauges detail, logs, security
   - **Tools** — skill/tool registry
   - **Channels** — Telegram/Signal feed preview
5. Theme switcher — stays bottom-right floating
6. Command input — sticky at bottom (full-width text field with `.gundam-holo` border)

**The real mobile control surface = Telegram / Signal** (already configured in Hermes, will be replicated in Gundam Halo):
- Phone web dashboard = **monitoring** (read project status, gauges, memory)
- Phone agent control = **chat** (Telegram/Signal bot — invoke, ask, get responses)
- This avoids the problem of forcing a multi-panel cockpit UI into a 3.5" screen

**Why this split**: Telegram/Signal UX is purpose-built for phones. Trying to make the web dashboard do both "visual overview" and "agent control" on a phone compromises both. Better to specialize each surface.

---

## 4. Pages / views

### 4.1 `/` — Cockpit overview (default landing)

The first-person cockpit layout above. No active project selected.

- Center: empty state with reticle + prompt "SELECT PROJECT TO INITIATE" (using `gundam-glitch-text` for the empty state, low pulse)
- Top-left: list of recent projects (3-5 most recent, with status indicators)
- Right: Mac system gauges
- Bottom: recent activity stream (collapsed by default)

### 4.2 `/projects/:id` — Project detail (primary use)

Same cockpit layout, but the **center is now the active project's chat** + agent output. Specifically:

- Center (large): chat messages (user ↔ agent) + agent "thinking" state (reticle spinner)
- Top-left: project breadcrumb + name (large, `gundam-text-neon`)
- Top-right: project status (active / idle / archived) + ring progress for "completeness"
- Middle-left: tools used in this project (skill/tool registry, with status)
- Middle-right: per-project memory indicator (count, last accessed)
- Bottom: command input (gundam-styled chat input)

### 4.3 `/projects/:id/memory` — Memory browser

- Lists all memory entries (conversations, file references, tool calls, decisions)
- Each entry is a `.gundam-hud-card` with timestamp + tag + content preview
- Top: search/filter (skill chips, date range)
- Right: Holo panel with "memory stats" (size, last accessed, related projects)

### 4.4 `/projects/new` — New project wizard

- 3-step: name + description → initial preset selection → mac control permissions
- Each step is a full-width `.gundam-hud-card` with `data-stream-scroll` for visual interest
- Progress at top: ring progress (`.gundam-ring-progress`) showing step 1/3, 2/3, 3/3

### 4.5 `/settings` — Settings

- Tabs: General · Mac Control · Channels · Themes · Security
- General: default project preset, agent type, MiniMax model
- Mac Control: file path policy, shell allowlist, Accessibility API permission
- Channels: Telegram bot token, Signal config, Tailscale hostname
- Themes: theme picker preview (shows all 8 themes as live mini-cards)
- Security: audit log, allowed chat IDs, command log

---

## 5. Component inventory

### From `templates/gundam.css` (the canonical base — copy this file)

| CSS class | Used in Gundam Halo for |
|---|---|
| `.gundam-hud-card` | Project list items, memory entries, settings panels (everywhere we need a "panel") |
| `.gundam-cockpit-frame` | The dashboard root frame (glass reflection, blurred backdrop) |
| `.gundam-radar` | Active agent activity radar (60-80px circles) |
| `.gundam-mini-radar` (SVG variant) | Settings pages, more detailed mini-radar visualizations |
| `.gundam-energy-bar` + `.gundam-energy-bar-fill` | Project "energy" (how active), Mac memory bar |
| `.gundam-gauge-v` | Mac CPU / RAM / disk / network (vertical gauges, 4 of them on right side) |
| `.gundam-ring-progress` | Project completion %, "step N of M" in wizards |
| `.gundam-reticle` | Center focus wrapper on project detail (concentric rings + crosshair) |
| `.gundam-holo-panel` | Floating windows (Telegram/Signal feed, system notifications) |
| `.gundam-status-ok/warn/alert` | Project status, tool status, channel status indicators |
| `.gundam-scanlines` | Optional overlay on inactive panels (gives "CRT" feel) |
| `.gundam-pulse` | Active project "I'm running" indicator |
| `.gundam-glitch-text` | System titles ("GUNDAM HALO // COCKPIT ONLINE"), empty states |
| `.gundam-hex-bg` | Dashboard root background (subtle hex grid pattern) |
| `.gundam-holo` | Floating windows (adds flicker) |
| `.gundam-scan` | Top-of-screen scanning line (system "scanning" effect) |
| `.gundam-target` | Active project "lock" indicator |
| `.gundam-damage-overlay` | Triggered on security alert / system error |

### Mode-specific animations (NT-D default)

- `.gundam-pulse` → `psychoframePulse` (2s pink pulse) — applied to active project card
- `.gundam-scanlines` (optional) — gives "psychoframe" texture
- Default scan overlay (`.gundam-scan`) — 4s scanningLine loop at top of screen

### Theme switcher widget

Use as-is from `SKILL.md` lines 1437-1475 (the 72px button + 8 mode buttons + OFF).

---

## 6. Implementation

### Tech stack alignment (from `README.md`)

- **Vite + React 19 + shadcn/ui + Tailwind v4 + Tauri 2**
- TypeScript (~5.7), React Router 7, Zustand (state), Sonner (toasts)

### CSS architecture

1. **Copy `~/workspace/gundam-design/templates/gundam.css`** to `frontend/src/styles/gundam.css` (do not modify the original in the skill folder).
2. **Import it once in `frontend/src/main.tsx`**: `import './styles/gundam.css';`
3. **Don't put Gundam styles in Tailwind's `@layer`** — let them live as plain CSS so the attribute selectors work cleanly.
4. **Tailwind for layout, Gundam for visuals**: use Tailwind for spacing/grid/flexbox, use `.gundam-*` classes for the visual treatment.
5. **shadcn components inside `.gundam-hud-card`**: shadcn primitives (Button, Input, Dialog) can be wrapped in `.gundam-hud-card` to inherit the cockpit styling.

### Font loading

In `frontend/index.html` `<head>`:
```html
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@700&family=Rajdhani:wght@600&family=Exo+2:wght@400&display=swap" rel="stylesheet">
```

(Could also use `@fontsource-variable/geist` which is already in OpenJarvis's stack, but for the cockpit aesthetic, Orbitron + Rajdhani + Exo 2 is more on-brand.)

### Default theme on boot

In `frontend/src/main.tsx`:
```tsx
// Set default theme BEFORE React renders to avoid flash
document.documentElement.setAttribute('data-theme', 'gundam-ntd');
```

Then read user override from `~/.gundam-halo/config.toml` and apply.

### Layer stack (z-index convention from skill)

| z | Element |
|---|---|
| 9999 | Theme switcher button |
| 9997 | Scanline overlay |
| 9996 | Glitch overlay |
| 9995 | Toast notifications (Sonner) |
| 8888–8889 | HUD corners + emblem badge |
| 100 | Burst corner effects |
| 50 | Warp speed streaks |
| 10 | Floating holo panels |
| 5 | Background effects (hex grid) |
| 1 | MS silhouette (faint, optional) |
| 0 | Normal content |

### 6.7 Desktop (Tauri) behavior (locked 2026-06-05)

**Strategy: single Tauri 2 app + menu bar tray icon. No separate floating panel for v1.**

**Why not a separate floating panel**:
- Maintenance cost is high (two UIs, two state trees, two routing schemes)
- "Floating panel is useful" is a pain you'd only feel after NOT having it — speculative v1 features often miss
- Mac-native feel is already delivered by a **menu bar tray icon** + the same dashboard

**What we build for v1**:
- **Tauri 2 main window** — hosts the same React app (no separate desktop code, full code reuse)
- **Tauri 2 tray icon** — sits in the Mac menu bar, persistent
  - Click → focus existing window (or open new if closed)
  - Right-click menu: "Open Dashboard" / "Quick Status" / "Quit"
- **Keyboard shortcut** (configurable, default `⌥Space` like Spotlight) — call dashboard to front
- **Window state persistence** — remember size/position across launches (Tauri's `tauri-plugin-window-state`)

**Configurable in `~/.gundam-halo/config.toml`**:
```toml
[desktop]
shortcut = "Alt+Space"   # global hotkey to summon dashboard
start_minimized = false  # launch hidden in tray, or show window
tray_icon = "default"    # allow per-theme tray icons later (NT-D emblem / SEED wing etc.)
```

**Out of scope for v1** (v2 if needed):
- "Always-on-top mini panel" mode — only add if we genuinely feel the pain of context-switching to a full window
- Multiple windows / workspaces per project — over-engineered for single-user

---

## 7. Asset integration

### Source asset library

**Path**: `/Users/kencheng/hermes-workspace/assets/gundam-assets/` (363 files across 24 categories — see `SKILL.md` for full manifest).

### What we need for v1

The cockpit UI works **without any image assets** — it's all CSS-driven (radar, gauges, reticles, holo panels are pure CSS). So image assets are **optional polish**, not required.

If we add them, prioritize:
- `02-ui-components/hud-frames/hud-corner-tl.png` + `hud-corner-br.png` — corner decorations
- `01-icons/emblems/emblem-ntd.png` — top-left emblem (default theme)
- `04-backgrounds/core-unicorn/bg-ntd-psychoframe-*.jpg` — **optional background** (4 JPGs, random-pick OR user-selectable in Settings) — see locked decision §8 #2

### Copy pattern (if/when we add assets)

```bash
SRC="/Users/kencheng/hermes-workspace/assets/gundam-assets"
DEST="frontend/public/gundam-assets"
mkdir -p "$DEST"
# Copy what's needed
cp "$SRC/02-ui-components/hud-frames/hud-corner-tl.png" "$DEST/"
cp "$SRC/02-ui-components/hud-frames/hud-corner-br.png" "$DEST/"
cp "$SRC/01-icons/emblems/emblem-ntd.png" "$DEST/"
# Then reference as /gundam-assets/hud-corner-tl.png in components
```

---

## 8. Locked product decisions

All 5 open decisions from the previous version of this doc — now locked 2026-06-05.

| # | Decision | Choice | Reasoning |
|---|---|---|---|
| 1 | **Theme scope** | **Per-user only** | Single-user project (Ken). Per-project adds complexity for no v1 benefit. |
| 2 | **Background image** | **Both — user-toggleable** | Default: pure CSS hex grid (no extra asset, fast, accessible). Optional: switch to one of 4 NT-D psychoframe JPGs from `04-backgrounds/core-unicorn/`. Toggle exposed in `/settings → General`. |
| 3 | **Sonner toast style** | **Themed** | Cyan/pink borders + glow on success/info, danger-red on error. Match the cockpit aesthetic. |
| 4 | **Mobile layout** | **Responsive cockpit + Telegram/Signal as primary phone control** | Detailed in [§3.5](#35-responsive--mobile-behavior-locked-2026-06-05). Vertical stack on phone, gauges collapse to single horizontal bar, sections become tabs. Telegram/Signal bot is the real phone UX. |
| 5 | **Tauri desktop app** | **Single Tauri app + menu bar tray icon** | Detailed in [§6.7](#67-desktop-tauri-behavior-locked-2026-06-05). No separate floating panel for v1 — that pain point is speculative. Tray icon + global hotkey cover the "summon from anywhere" use case. |

**Result**: all 5 decisions are locked. Doc is implementation-ready. We can proceed to `ARCHITECTURE.md` and then scaffold `backend/` + `frontend/`.

---

## 9. References

| Path | What |
|---|---|
| `~/workspace/gundam-design/SKILL.md` | Main skill spec (1665 lines) — **read this first** |
| `~/workspace/gundam-design/templates/gundam.css` | Quick-start CSS template (220 lines) — **copy this to `frontend/src/styles/gundam.css`** |
| `~/workspace/gundam-design/references/static-site-integration.md` | Critical: do NOT manipulate React classes — use `data-theme` attribute only |
| `~/workspace/gundam-design/references/hud-ui-prompts.md` | Asset generation prompts (only if we need more images) |
| `~/workspace/gundam-design/references/cartoon-ui.md` | Cartoon kawaii assets (if user wants kawaii theme at some point) |
| `~/workspace/gundam-design/references/manifest.md` | Full asset manifest (363 files) — for future reference |
| `~/workspace/gundam-design/assets/` | Sample PNG/JPEG assets to look at |
| `~/hermes-workspace/assets/gundam-assets/` | Production asset library (source for `cp` commands above) |
| `../OpenJarvis/frontend/` | Reference: existing Vite + React 19 + shadcn + Tauri 2 stack (the same stack we're using) |
| `../README.md` | This repo's README — overall project context |

---

## 10. Changelog

| Date | Change |
|---|---|
| 2026-06-05 | Initial design spec. Default theme NT-D / Unicorn. First-person cockpit layout. 5 pages defined. Component inventory mapped. |
| 2026-06-05 | Locked all 5 open decisions. Added §3.5 (responsive/mobile) and §6.7 (Tauri desktop) as concrete strategies. Replaced "Open decisions" with "Locked product decisions" table. Doc is now implementation-ready. |
| 2026-06-10 | **Settings tabs expanded to 7**: General · Mac Control · Channels · Themes · Security · Secrets (M6) · **User Memory (M7-Phase-2.5)**. New "User Memory" tab is a read-only viewer — left column shows user list (chip buttons), right column expands the selected user's memory entries (key as cyan mono code, value in body, updated/created timestamps below, "Delete" button for cleanup). Empty state copy: *"No users yet. Start a conversation — when the agent calls `memory_write`, you'll see the user here."* Follows the existing NT-D visual language (HudCard, Orbitron/Rajdhani, danger-red borders for destructive actions, gundam-radar spinner). New `frontend/src/types/api.ts` types: `MemoryEntry`, `MemoryUserList`, `MemoryUserEntries`. |

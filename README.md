# Gundam Halo

> **Personal AI agent on Mac.** Hermes-like feel, MiniMax brain, deep Mac control, per-project isolation. Cockpit-themed dashboard.

![Status: Planning](https://img.shields.io/badge/status-planning-yellow)
![License: MIT](https://img.shields.io/badge/license-MIT-green)

---

## Why this exists

**Hermes Agent is great, but it gets messy with too many projects.** Single agent, single growing context, no project boundaries. Once you have 3+ active threads, context bleed starts to hurt.

**Gundam Halo is the second system** that solves this — same Hermes-feel conversational UX, but:

- **Per-project isolation** (each project = its own session, memory, context, archive)
- **Web UI dashboard** (replaces CLI / Textual)
- **Deeper Mac control** (file I/O, shell allowlist, AppleScript, Accessibility API, etc.)
- **MiniMax API as the only LLM backend** (no model shopping)
- **Remote control from phone** via Telegram + Tailscale
- **Cockpit-themed UI** (8 switchable Gundam themes — see Design below)

**Coexists with Hermes.** Never touch `~/.hermes/`.

---

## Status

🚧 **Planning phase.** Dashboard design pending — see [Design](#design) below. No code yet. Wait for ARCHITECTURE.md before scaffolding.

---

## Architecture (planned)

```
┌────────────────────────────────────────────┐
│  Web UI  (Vite + React 19 + shadcn + Tauri)│
│  Telegram Bot                              │
│  Tailscale (remote)                        │
└──────────────────┬─────────────────────────┘
                   ↓ REST / WS
┌────────────────────────────────────────────┐
│  FastAPI Server  (Python 3.11+)            │
│  ┌──────────┬──────────┬──────────┬──────┐ │
│  │ Session  │ Project  │ Skills   │ Mac  │ │
│  │ Mgr      │ Workspace│ Registry │ Ctrl │ │
│  └────┬─────┴────┬─────┴────┬─────┴──┬───┘ │
│       └──────────┴──────────┴────────┘     │
│                  ↓                         │
│          MiniMax API (LLM brain)           │
└────────────────────────────────────────────┘
                   ↓
          Mac system
```

---

## Stack

| Layer | Choice |
|---|---|
| **Frontend** | Vite + React 19 + shadcn/ui + Tailwind v4 + Tauri 2 |
| **Backend** | FastAPI (Python 3.11+) |
| **LLM brain** | **MiniMax API** (OpenAI-compatible) |
| **Channels** | Telegram bot (primary), Signal (TBD) |
| **Remote access** | Tailscale (no public internet exposure) |
| **Storage** | Per-project workspace (path TBD) |
| **Project layout** | Forked from OpenJarvis architecture (registry + event bus + ABC contracts) |

### Mac control scope (all confirmed)

- File I/O (read/write anywhere, with path policy)
- Shell command execution (allowlist)
- `open <app>` to launch apps
- AppleScript automation
- Clipboard management
- System notifications
- Spotlight / file search
- Accessibility API (deep, requires permission)
- `git push` (handled by Mavis sub-agent)

---

## How this differs from siblings

| | **Hermes Agent** | **OpenJarvis** | **Gundam Halo (this)** |
|---|---|---|---|
| LLM | Nous Portal / OpenRouter / local vLLM | 5+ backends | **MiniMax only** |
| Context model | Single growing | Multi-agent, shared | **Per-project isolated** |
| UI | CLI + gateway daemon | Textual TUI + Web | **Web only, cockpit theme** |
| Mac control | Local terminal (basic) | Tools + security suite | **Deep (AppleScript, A11y, etc.)** |
| Scope | Personal AI, general | Research framework | **Personal Mac agent, focused** |
| Codebase | Independent | Independent | **Forks OpenJarvis architecture** |

---

## Design

Dashboard design lives at `~/workspace/gundam-design/`. The skill spec is `SKILL.md` (72KB, comprehensive design system).

**What we're getting:**

- 8 switchable Gundam themes:
  - NT-D / Unicorn (psychoframe)
  - SEED Freedom
  - Crossbone X-1
  - NT-D Green Frame
  - 00 Qubit
  - Destiny / Legend
  - God Gundam
  - Cartoon Kawaii
- 32 keyframe animations (scanning lines, target lock, damage flash, hex grid pulse, holo flicker, screen shake, data stream scroll, etc.)
- 363 assets across 24 categories (icons, HUD frames, gauges, radar, bursts, beams, backgrounds, MS silhouettes, etc.)
- 6 HTML+CSS component patterns (target reticle, gauges, rings, panels, radar, screen shake)
- CSS variable architecture + neon/glow techniques

**Asset library path:** `/Users/kencheng/hermes-workspace/assets/gundam-assets/`
**Manifest:** `/Users/kencheng/hermes-workspace/assets/gundam-assets/MANIFEST.md`

Theme will be selected at project init (or per-project, TBD).

---

## Project layout (planned)

```
gundam halo/
├── README.md                 # this file
├── .gitignore
├── ARCHITECTURE.md           # design decisions, will be written after dashboard design lands
├── backend/                  # FastAPI server
│   ├── app/
│   │   ├── main.py
│   │   ├── core/             # registry, events, config (forked from OpenJarvis)
│   │   ├── engines/          # MiniMax provider
│   │   ├── agents/           # per-project agent runners
│   │   ├── channels/         # Telegram / Signal bots
│   │   ├── mac/              # Mac control pane (file, shell, AppleScript, A11y)
│   │   ├── projects/         # workspace isolation
│   │   └── security/         # auth, audit, command allowlist
│   ├── tests/
│   └── pyproject.toml
├── frontend/                 # Vite + React 19 + shadcn
│   ├── src/
│   │   ├── components/
│   │   ├── pages/            # dashboard, project, settings, etc.
│   │   ├── stores/           # zustand
│   │   └── lib/
│   ├── src-tauri/            # Tauri 2 wrapper for desktop
│   └── package.json
└── deploy/                   # install scripts, Tailscale config, etc.
```

---

## Development

Coming once ARCHITECTURE.md is written. Setup will likely be:

```bash
# backend
cd backend
uv sync
uv run fastapi dev

# frontend
cd frontend
npm install
npm run dev

# desktop (optional)
npm run tauri dev
```

---

## Roadmap (rough)

1. ⏸️ Wait for dashboard design from `~/workspace/gundam-design/`
2. ⏸️ Write `ARCHITECTURE.md` (locks all design decisions)
3. ⏸️ Scaffold `backend/` (fork OpenJarvis minimal subset, swap engine to MiniMax)
4. ⏸️ Scaffold `frontend/` (Vite + React 19, cockpit theme baseline)
5. ⏸️ Mac control pane (file I/O + shell allowlist first, then AppleScript, A11y)
6. ⏸️ Per-project workspace isolation
7. ⏸️ Telegram bot + Tailscale auth
8. ⏸️ End-to-end test, deploy to user Mac

---

## Security notes

This system has **internet-facing shell access** via Telegram + Tailscale. The following are non-negotiable:

- All shell commands go through an **allowlist**
- All file writes go through a **path policy** (no writing to system dirs, SSH keys, etc.)
- **Per-action audit log** (who, what, when, what file/command)
- **Tailscale ACL** restricts which devices can reach the gateway
- **Telegram bot** only accepts commands from whitelisted chat IDs
- Accessibility API calls require explicit per-session grant

---

## Related

- `~/workspace/OpenJarvis/` — architecture reference (registry, event bus, multi-agent)
- `~/workspace/gundam-design/` — design system (SKILL.md, 363 assets, 8 themes)
- `~/.hermes/` — Hermes Agent data (do not touch)
- `~/hermes-workspace/assets/gundam-assets/` — Gundam design asset library

---

## License

[MIT](./LICENSE) — same as Hermes Agent. Do what you want, just keep the copyright notice.

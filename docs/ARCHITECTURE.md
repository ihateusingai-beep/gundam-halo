# Gundam Halo — Architecture

> **System architecture** for personal AI agent on Mac. Backend (FastAPI + MiniMax), frontend (Vite + React 19 + cockpit), Mac control pane, channels (Telegram/Signal), per-project isolation.

**Status**: 📐 Architecture spec — locks module structure, API surface, security model, data flow. Implementation will follow.

**Companion docs**:
- [`README.md`](../README.md) — project overview, stack, roadmap
- [`DASHBOARD.md`](./DASHBOARD.md) — UI/UX spec, themes, layouts, components

---

## 1. High-level architecture

```
┌─────────────────────────────────────────────────────────┐
│  PRESENTATION                                           │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐  │
│  │ Web UI       │  │ Tauri       │  │ Telegram Bot   │  │
│  │ (cockpit)    │  │ desktop app │  │ Signal Bot     │  │
│  └──────┬───────┘  └──────┬──────┘  └────────┬───────┘  │
│         │ HTTPS/WS       │ HTTPS/WS         │ HTTPS    │
└─────────┼─────────────────┼────────────────────┼─────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────┐
│  BACKEND (FastAPI)                                      │
│  ┌────────────────────────────────────────────────────┐ │
│  │ API layer (REST + WebSocket)                       │ │
│  ├────────────────────────────────────────────────────┤ │
│  │ ┌─────────┬──────────┬──────────┬────────────────┐ │ │
│  │ │ Session │ Project  │ Channel  │ Mac Control     │ │ │
│  │ │ Manager │ Workspace│ Adapter  │ (policy-gated)  │ │ │
│  │ └────┬────┴────┬─────┴────┬─────┴───────┬────────┘ │ │
│  │      │         │          │             │          │ │
│  │ ┌────┴─────────┴──────────┴─────────────┴───────┐  │ │
│  │ │ Agent layer (ReAct / Orchestrator / Simple)   │  │ │
│  │ │ Tools layer (file_read, shell, code, etc.)    │  │ │
│  │ └────────────────────┬──────────────────────────┘  │ │
│  │                      │                             │ │
│  │ ┌────────────────────┴──────────────────────────┐  │ │
│  │ │ Core (registry / events / types)              │  │ │
│  │ │ — forked from OpenJarvis                      │  │ │
│  │ └───────────────────────────────────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTPS
                          ▼
                ┌──────────────────────┐
                │  MiniMax API         │
                │  (LLM brain)         │
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Mac system          │
                │  (file / shell /     │
                │  AppleScript / A11y) │
                └──────────────────────┘
```

---

## 2. Project workspace filesystem

All runtime state lives under `~/.gundam-halo/`. Per-project isolation is the **fundamental unit**.

```
~/.gundam-halo/
├── config.toml                   # User config (TOML)
├── projects/
│   └── <project-name>/
│       ├── project.toml          # Metadata
│       ├── memory/
│       │   ├── short-term.jsonl  # Recent conversations
│       │   ├── long-term.db      # SQLite (FAISS-ready later)
│       │   └── embeddings/       # Cached embeddings
│       ├── conversations/
│       │   └── <session-id>.json
│       ├── files/                # Files referenced/created
│       ├── tools/                # Tool execution logs
│       │   └── <tool-call-id>.json
│       ├── checkpoints/          # Resume points
│       └── state.json            # Current session state
├── archive/
│   └── <project-name>/
│       └── <snapshot>/
├── logs/
│   ├── audit.log                 # All Mac control actions (immutable)
│   ├── system.log
│   ├── security.log
│   └── channel/
│       ├── telegram.log
│       └── signal.log
└── cache/
```

### `config.toml` shape

```toml
[user]
name = "Ken"
default_theme = "gundam-ntd"

[llm]
provider = "minimax"
api_key_env = "MINIMAX_API_KEY"     # read from env, NEVER stored in TOML
base_url = "https://api.MiniMax.chat/v1"
default_model = "MiniMax-M3"
fallback_model = "MiniMax-M2"

[server]
host = "0.0.0.0"
port = 8765                        # bound, but only reachable via Tailscale

[desktop]
shortcut = "Alt+Space"
start_minimized = false
tray_icon = "default"

[tailscale]
hostname = "gundam-halo"
acl_required = true                # reject non-Tailscale connections

[mac_control]
default_path_policy = "project_only"   # or "user_home", "allowlist"
shell_allowlist = [
    "git", "ls", "cat", "head", "tail",
    "grep", "rg", "find", "fd",
    "pwd", "cd", "echo", "date",
    "open",                                  # `open <app>`
]
file_read_paths = ["~/Documents", "~/Downloads", "~/workspace", "/tmp"]
file_write_paths = ["~/workspace", "~/.gundam-halo/projects"]
a11y_enabled = false
apple_script_enabled = true
notifications_enabled = true

[channels.telegram]
enabled = true
bot_token_env = "GUNDAM_HALO_TG_TOKEN"
allowed_chat_ids = [123456789]      # whitelist (your chat ID)
command_prefix = "/"

[channels.signal]
enabled = false                    # v1: stub
daemon_socket = "/var/run/signal-cli/socket"
allowed_phone_numbers = ["+852-XXXX-XXXX"]

[security]
audit_log = "~/.gundam-halo/logs/audit.log"
audit_max_size_mb = 100
injection_scan = true
require_confirm_for = [
    "mac.file.write",
    "mac.shell",
    "mac.apple_script",
    "mac.a11y",
]
```

### Per-project `project.toml`

```toml
[project]
name = "fix-jarvis-memory-leak"
created_at = "2026-06-05T10:00:00Z"
status = "active"                  # active | paused | archived
agent_type = "native_react"
theme_override = null              # null = use user default
default_paths = ["~/workspace/jarvis/src/jarvis/memory/"]
allowed_apps = []
```

---

## 3. Repository layout (planned)

```
gundam-halo/
├── README.md
├── LICENSE                        # MIT
├── .gitignore
├── docs/
│   ├── DASHBOARD.md               # ✅ done
│   └── ARCHITECTURE.md            # ✅ this file
├── backend/                       # FastAPI + Python
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                  # registry, events, types, config, logging
│   │   ├── engines/
│   │   │   ├── minimax.py         # MiniMax API provider (new)
│   │   │   └── _stubs.py
│   │   ├── agents/                # native_react, orchestrator, simple
│   │   ├── projects/              # manager, workspace, session, archive
│   │   ├── channels/              # base, telegram, signal, manager
│   │   ├── mac/                   # control + policy + ops modules
│   │   ├── security/              # auth, audit, scanner, allowlist
│   │   ├── api/                   # REST routes + WebSocket
│   │   └── bridge/
│   │       └── mavis.py           # bridge to Mavis sub-agent
│   ├── tests/
│   └── pyproject.toml
├── frontend/                      # Vite + React 19 + Tauri 2
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/                # index, projects/[id], settings
│   │   ├── components/
│   │   │   ├── ui/                # shadcn primitives
│   │   │   ├── gundam/            # cockpit-specific
│   │   │   └── layout/            # CockpitLayout, TopBar, etc.
│   │   ├── stores/                # Zustand
│   │   ├── lib/                   # api, ws, utils
│   │   ├── styles/gundam.css      # copy of templates/gundam.css
│   │   └── types/
│   ├── public/gundam-assets/      # optional images
│   ├── src-tauri/                 # Tauri 2 shell
│   └── package.json
├── deploy/
│   ├── install.sh
│   ├── install.ps1
│   ├── tailscale-acl.example
│   └── gundam-halo.service.example
└── tests/e2e/                     # end-to-end Playwright
```

---

## 4. Backend — module details

### 4.1 Core (forked from OpenJarvis)

Adopt OpenJarvis's core verbatim — it's already clean:

- `core/registry.py` — generic typed registry (Agent, Channel, Engine, Tool, Memory, ...)
- `core/events.py` — pub/sub event bus, thread-safe, optional history
- `core/types.py` — shared types (Message, Role, ToolCall, ToolResult)
- `core/config.py` — TOML loading with env-var substitution
- `core/logging.py` — structured JSON logging

**Why fork instead of pip install**: tighter version control, can patch in-place.

### 4.2 Engines — `engines/`

MiniMax provider (new, OpenAI-compatible):

```python
# engines/minimax.py
from openai import OpenAI
from openjarvis.core.types import Message

class MiniMaxEngine:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def chat(self, messages: list[Message], tools: list = None) -> Message:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[m.to_dict() for m in messages],
            tools=tools or [],
        )
        return Message.from_response(response)
```

### 4.3 Agents — `agents/`

Three agent types, registered via `AgentRegistry`:

| Agent | Loop | Use case |
|---|---|---|
| `simple` | Single-turn | Quick Q&A, no tools |
| `native_react` | Thought → Action → Observation | Default for most projects |
| `orchestrator` | Multi-step planning + tool selection | Complex multi-tool tasks |

Each agent is per-project (one agent per session).

### 4.4 Projects — `projects/`

- `manager.py` — create / list / archive / delete projects
- `workspace.py` — per-project FS layout (creates directories, manages paths)
- `session.py` — session lifecycle (start, save state, resume, stop)
- `archive.py` — tar + compress project on archive

### 4.5 Channels — `channels/`

Abstract `BaseChannel` with subclasses for Telegram and Signal. Each channel:
- Receives inbound messages
- Identifies sender (whitelist check)
- Routes to active session (or creates new)
- Sends outbound responses

Channel registry (`ChannelRegistry`) — both are pluggable.

### 4.6 Mac Control — `mac/` (the security-sensitive part)

See [§6 Mac control pane architecture](#6-mac-control-pane) below.

### 4.7 Security — `security/`

- `auth.py` — Tailscale-aware (verify request comes via Tailscale IP, check ACL tag)
- `audit.py` — append-only audit log to `~/.gundam-halo/logs/audit.log`
- `injection_scanner.py` — scans inbound text for prompt injection patterns
- `allowlist.py` — shared allow/deny logic (used by mac/policy.py)

### 4.8 Bridge — `bridge/mavis.py`

Bridge to Mavis (me) for coding sub-tasks. Approach (v1):
- Spawn Mavis as a subprocess via `mavis communication send`
- Pass task context (file path, project, git remote)
- Mavis returns diff/commit info
- Bridge returns formatted response to the agent

---

## 5. Frontend — module details

### 5.1 Routes (React Router 7)

```
/                          → routes/index.tsx (cockpit overview)
/projects/new              → routes/projects/new.tsx
/projects/:id              → routes/projects/[id].tsx (project detail)
/projects/:id/memory       → routes/projects/[id]/memory.tsx
/settings                  → routes/settings.tsx
```

### 5.2 Stores (Zustand)

- `theme.ts` — current theme + setTheme
- `projects.ts` — list of projects, current project, CRUD
- `session.ts` — current session state, messages
- `system.ts` — Mac gauges (subscribed via WebSocket)

### 5.3 Gundam components (cockpit-specific)

Reusable React components wrapping the gundam CSS classes from `templates/gundam.css`:

- `HudCard.tsx` — wraps `.gundam-hud-card`
- `Radar.tsx` — `.gundam-radar` with React state for sweep angle
- `Gauge.tsx` — `.gundam-gauge-v` with value prop
- `RingProgress.tsx` — `.gundam-ring-progress` (SVG-based)
- `Reticle.tsx` — `.gundam-reticle` wrapper
- `HoloPanel.tsx` — `.gundam-holo-panel` with collapse
- `StatusDot.tsx` — `.gundam-status-ok/warn/alert`
- `EnergyBar.tsx` — `.gundam-energy-bar`
- `ThemeSwitcher.tsx` — the skill's 8-mode switcher (React port)
- `CommandInput.tsx` — sticky bottom chat input

### 5.4 Layouts

- `CockpitLayout.tsx` — full desktop cockpit (grid)
- `MobileLayout.tsx` — vertical stack (see DASHBOARD.md §3.5)
- `TopBar.tsx`, `RightPanel.tsx`, `LeftPanel.tsx`, `BottomBar.tsx` — cockpit regions

### 5.5 Tauri shell

Tauri 2 config:
- Main window: full dashboard
- Tray icon: persistent (see §5.5.1)
- Global hotkey: `⌥Space` (configurable) → focus dashboard
- Window state persistence (size/position)
- No separate floating panel in v1

#### 5.5.1 Tray icon (Unicorn Gundam Psycho-Frame — animated)

The agent lives in the macOS menu bar so the dashboard is always one click
away without stealing focus from the user's current work. The tray icon is
an **animated 5.86 s loop** showing the Unicorn Gundam head awakening in
green Psycho-Frame — calm golden horn + green eyes, building energy, peak
explosion with energy wings, and back to calm.

**Static icon** (used for the app bundle, dock, ⌘Tab, and as the initial
tray frame before the animation thread starts):

| File | Size | Purpose |
|---|---|---|
| `icons/icon.png` | 1024×1024 | Master; calm-state Gundam head (frame 0) |
| `icons/32x32.png` | 32 | Tauri bundle |
| `icons/128x128.png` | 128 | Tauri bundle |
| `icons/128x128@2x.png` | 256 | Tauri bundle (retina) |
| `icons/icon.icns` | multi | macOS app bundle |
| `icons/icon.ico` | multi | Windows app bundle (16→256) |

**Animated frames** (used by the tray at runtime):

| Path | Contents |
|---|---|
| `icons/anim/frame_001.png` ... `frame_088.png` | 88 frames @ 15 FPS, 256×256 RGBA, seamless loop |

Total embedded size: ~7.3 MB. The frames are compiled into the binary via
`include_dir!($CARGO_MANIFEST_DIR/icons/anim)` so the production build needs
no extra resources to animate the tray.

**Generation pipeline** (`scripts/generate_tauri_icons.py`):

1. Generate a 2K calm-state Unicorn Gundam head via `matrix_generate_image`.
2. Use it as the `first_frame` reference for a 6 s awakening video via
   `matrix_gen_videos` (calm → peak → calm, seamless loop).
3. `ffmpeg` extracts 15 FPS frames at 256² (LANCZOS resample).
4. `frame_001.png` is reused as the static master, resized to all Tauri
   bundle sizes and packed into `.icns` (via macOS `iconutil`) and `.ico`.

**Animation driver** (`src-tauri/src/lib.rs`):

- `load_animation_frames()` decodes every `icons/anim/frame_*.png` into
  `tauri::image::Image<'static>` at startup (~5.7 MB steady-state heap).
- `spawn_animation_thread()` runs a dedicated `halo-tray-anim` thread that
  calls `tray.set_icon(Some(frames[i]))` every `1000 / fps` ms and loops.
- The current FPS is stored in a process-wide `AtomicU32`
  (`ANIMATION_FPS`, default 15) and re-read on every tick, so
  `set_animation_speed(fps)` takes effect on the next frame — no thread
  restart, no icon glitch.
- An `Arc<AtomicBool>` stop flag is stashed in `app.manage(AnimationStop(..))`
  for future pause hooks (battery saver, focus-state pause).
- `tauri::image::Image::set_icon` is `Send + Sync` and uses internal locks,
  so it is safe to call from a non-main thread on macOS and Windows.

**Runtime FPS tuning** (M3-B7):

The tray animation cadence is exposed via two Tauri commands,
registerable from the frontend and callable from the browser console:

| Command | Signature | Description |
|---|---|---|
| `set_animation_speed` | `(fps: u32) -> u32` | Set the FPS. Clamped to `[1, 60]`. Returns the effective value. |
| `get_animation_speed` | `() -> u32` | Read the current FPS (post-clamp). |

Frontend wrapper: `frontend/src/services/halo-tray-controls.ts`
exposes `setAnimationSpeed(fps)` / `getAnimationSpeed()` and a
`window.__haloTray` debug global:

```ts
await __haloTray.setAnimationSpeed(8)    // battery saver
await __haloTray.setAnimationSpeed(24)   // cinema smooth
await __haloTray.getAnimationSpeed()     // → 24
```

Recommended presets for the settings UI (M3-B8):

| Preset | FPS | When to use |
|---|---|---|
| Battery saver | 8 | On battery, low-power mode, long idle |
| Smooth | 15 (default) | Day-to-day, perceptibly smooth |
| Cinema | 24 | Active session, you want the loop to feel alive |

The settings UI lives in the existing **General** tab of the Settings
page (`/settings`). A new "Tray Icon Animation" section shows:
- A live FPS read-out (large Orbitron digits, cyan)
- A continuous slider (1–60) wired to the same Tauri command
- Three preset chips (Battery Saver / Default / Cinema) for quick select
- A note that the value resets to 15 on app restart (persistence in v1.1)

The slider fill is driven by a CSS custom property
(`--gundam-slider-fill`) so the track lights up cyan to the current
position, matching the cockpit HUD aesthetic. Toast confirmation on
change shows the effective value (post-clamp) so the user sees
exactly what the runtime ended up using.

#### 5.5.1.1 Secrets management (M6+)

The Settings page has a dedicated **Secrets** tab (⚿ icon) for
managing runtime secrets — currently the MiniMax API key and the
Telegram bot token. Previously these had to be set via `~/.gundam-halo/.env`
file or environment variable, which is awkward for a "local project
with secrets managed in the UI" workflow. M6 replaces that with a
dashboard-driven flow that:

1. **Persists to `~/.gundam-halo/.env`** with `0600` permissions via
   an atomic write (tmp file + `os.replace`).
2. **Mirrors into `os.environ`** so the running process picks up new
   values via the standard `os.environ.get` path.
3. **Invalidates the config cache** so the next LLM / Telegram
   request reloads the new value — no server restart required.

**API contract** (`app/api/secrets.py`):

| Verb | Path | Body | Returns |
|---|---|---|---|
| GET | `/api/secrets` | — | `{<NAME>: {label, configured, source}}` — never the value |
| POST | `/api/secrets` | `{secrets: [{name, value}]}` | Updated status map |
| DELETE | `/api/secrets/{name}` | — | Updated status map |
| POST | `/api/secrets/clear` | `{names: [...]}` | Updated status map |

**Security properties** (verified by `tests/core/test_secrets_store.py`):

- The server **never** returns a secret value in any response.
  `test_response_never_includes_value` asserts this even when the
  value is leaked into a `caplog` record.
- Unknown / unsafe env-var names are rejected at the API boundary.
- The `.env` file is `0600`-permissioned; unsafe-name regex
  (`^[A-Z][A-Z0-9_]*$`) prevents shell injection.
- The in-memory override map is read on every `get()` call (no
  caching), so POST → next request latency is < 1 ms.
- The frontend inputs use `autocomplete="off"`, `data-1p-ignore`,
  and `data-bwignore` to discourage password-manager capture.
  Saved values are cleared from local state immediately after a
  successful save.

**Reload semantics** (subtle but important):

- `cfg = get_config()` is cached at module level. On POST, we
  set `config_mod._config = None` so the next `get_config()` call
  reloads from disk + env. The in-memory override map is the
  immediate source of truth, so even between the cache invalidation
  and the next reload there's no window where the new value is
  invisible.
- This means **LLM and Telegram engine instances constructed during
  process startup will not see the new value until the next time
  they call `get_config()`**. The Telegram channel hot-reloads via
  `cfg.telegram.bot_token` on every message dispatch; the LLM engine
  caches its key in the constructor but re-reads on
  `MiniMaxEngine(...)` calls. For best results, the user should
  restart the server after a key change for a long-running session,
  but in practice the next-message pickup is fast enough for
  single-user interactive use.

**Menu** (right-click on tray icon):

| Item | Accelerator | Action |
|---|---|---|
| Open Dashboard | — | Show + focus the main window |
| Hide to Tray | — | Hide the main window (agent keeps running) |
| ─── | | |
| New Chat | ⌘N | Show window + emit `halo://new-chat` to frontend |
| Settings… | ⌘, | Show window + emit `halo://open-settings` |
| ─── | | |
| Quit Gundam Halo | ⌘Q | `app.exit(0)` (clean shutdown) |

**Interactions**:
- **Tray icon left-click** → toggle window visibility (no menu).
- **Tray icon right-click** → open the menu above.
- **Window close button (red traffic light)** → hide to tray, **not quit**.
  Quit must be explicit via the tray menu so background work continues.
- **`--minimized` flag** (set by the autostart plugin on login) → start
  hidden in the tray.
- **macOS dock click** while hidden → the window re-opens via Tauri 2's
  default re-activation (Reopen run event).

**Capabilities** (`src-tauri/capabilities/default.json`): `core:tray:default`,
`core:window:default` (+ allow-set-focus, allow-show, allow-hide),
`core:event:default` (for `halo://*` events), `core:webview:default`.

**Crate features**: `tauri = { version = "2", features = ["tray-icon", "image-png"] }`
+ `image = "0.25"` + `include_dir = "0.7"`.

---

## 6. Mac control pane

The most security-sensitive module. Default-deny, policy-gated, audited.

### 6.1 Layered architecture

```
┌────────────────────────────────────────┐
│  mac/control.py  (public interface)    │  ← only entry point
│  - one method per operation            │
├────────────────────────────────────────┤
│  mac/policy.py   (authorization)       │  ← every op checks here FIRST
│  - path policy                         │
│  - command allowlist                   │
│  - per-project restrictions            │
├────────────────────────────────────────┤
│  mac/file_ops.py, shell.py, ...        │  ← actual implementations
│  (one module per op type)              │
├────────────────────────────────────────┤
│  security/audit.py                     │  ← every op logged
│  (append-only, immutable)              │
└────────────────────────────────────────┘
```

### 6.2 Operations (locked scope)

| Operation | Module | Policy check | Audit? |
|---|---|---|---|
| Read file | `file_ops.read()` | path in `file_read_paths` | Yes |
| Write file | `file_ops.write()` | path in `file_write_paths` | **Yes + confirmation** |
| Shell exec | `shell.run()` | command in `shell_allowlist` | **Yes + confirmation** |
| `open <app>` | `apple_script.open_app()` | app in `allowed_apps` | Yes |
| AppleScript | `apple_script.run()` | script validated | **Yes + confirmation** |
| Spotlight | `spotlight.search()` | none (read-only OS API) | Yes |
| Clipboard get/set | `clipboard.get/set()` | none | Yes |
| Notifications | `notifications.send()` | none | Yes |
| Accessibility API | `a11y.*` | requires `a11y_enabled` + per-session grant | **Yes + confirmation** |
| `git push` | `git.push()` | delegates to Mavis | **Yes + confirmation** |

### 6.3 Audit log format (NDJSON, append-only)

```json
{"ts":"2026-06-05T10:23:45Z","actor":"session:abc123","action":"mac.file.read","target":"/Users/ken/workspace/foo.py","result":"ok","duration_ms":12}
{"ts":"2026-06-05T10:23:51Z","actor":"channel:telegram:user:123","action":"mac.shell","target":"git status","result":"ok","duration_ms":340}
```

### 6.4 Mavis delegation (git push)

`git push` is special — it requires:
1. Read the local diff
2. Generate a meaningful commit message (LLM task)
3. Run `git add`, `git commit`, `git push`

This is **exactly** my (Mavis's) wheelhouse. The flow:
1. Agent decides "I need to push X"
2. `mac/git.push()` is called → delegates to `bridge/mavis.py`
3. Bridge calls Mavis via `mavis communication send` with task + context
4. Mavis does the work, returns commit SHA + push result
5. Agent formats response

---

## 7. API surface (FastAPI)

### REST

```
GET    /api/projects                      # list all
POST   /api/projects                      # create new
GET    /api/projects/{id}                 # detail
DELETE /api/projects/{id}                 # delete (with archive)
POST   /api/projects/{id}/archive         # archive
GET    /api/projects/{id}/memory          # browse memory
GET    /api/projects/{id}/conversations   # chat history

POST   /api/sessions                      # start new session in a project
GET    /api/sessions/{id}                 # session state
POST   /api/sessions/{id}/message         # send user message → agent
POST   /api/sessions/{id}/stop            # stop session

GET    /api/mac/system                    # gauges (CPU/RAM/disk/network)
POST   /api/mac/file/read                 # read file
POST   /api/mac/file/write                # write file
POST   /api/mac/shell                     # shell exec
POST   /api/mac/open                      # open app
POST   /api/mac/applescript               # run AppleScript
POST   /api/mac/clipboard/get
POST   /api/mac/clipboard/set
POST   /api/mac/notification
POST   /api/mac/spotlight
POST   /api/mac/a11y/query
POST   /api/mac/git/push                  # delegates to Mavis

GET    /api/channels                      # list channels + status
POST   /api/channels/telegram/test
GET    /api/channels/telegram/status

GET    /api/security/audit                # browse audit log (paginated)
GET    /api/security/audit?action=mac.shell

GET    /api/config                        # get current config (secrets redacted)
PUT    /api/config                        # update config
```

### WebSocket — `/ws`

Real-time push from backend to frontend:
- `system.gauges` (every 2s) — CPU/RAM/disk/network
- `agent.thinking` — agent is processing
- `agent.message` — new message from agent
- `agent.tool_call` — agent is calling a tool
- `session.state_change` — session state transitions
- `security.alert` — injection detected, action blocked

---

## 8. MiniMax integration

MiniMax API is OpenAI-compatible. Use the `openai` Python SDK with a custom `base_url`:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://api.MiniMax.chat/v1",
    api_key=os.environ["MINIMAX_API_KEY"],
)

response = client.chat.completions.create(
    model="MiniMax-M3",                  # configurable in config.toml
    messages=[...],
    tools=[...],                          # function calling for our tools
    stream=True,                          # stream to client via WebSocket
)
```

**Features used**:
- Chat completions (with streaming)
- Function calling (for tools)
- (No vision / image gen needed in v1)

---

## 9. Channel integration

### Telegram (M4 — shipped)

Telegram is Gundam Halo's **primary phone control surface** (per
locked product decision §13). It runs the same agent as the web
dashboard, but each Telegram chat gets its own persistent session in
the `telegram` project — your DMs and group chats don't bleed into
each other.

- Library: `python-telegram-bot` v22+
- Bot token from `GUNDAM_HALO_TG_TOKEN` env var (empty → **dry-run** mode for development)
- Whitelist: only allowed `chat_ids` (configured via `config.toml [telegram] allowed_chat_ids`)
- **Mode auto-detected**:
  - `real` if `bot_token` is set → connects to Telegram and long-polls
  - `dry-run` otherwise → no network, `send()` only logs, useful for local dev/tests
- **Commands** (intercepted before agent dispatch):
  - `/help` — list commands + capabilities
  - `/new` — reset this chat's session (drops cached agent, fresh conversation)
  - `/status` — show current session metadata (id, started_at, last_active, message_count)
  - `/echo` — debug marker
  - _Anything else_ → routed to the agent as a normal message
  - _Unrecognized command_ → falls through to the agent (so the agent can answer "I don't know that command")

#### Architecture (M4)

```
┌────────────────────────────────────────────────────────────────┐
│  Telegram Bot API (cloud)                                       │
└─────────────────────┬──────────────────────────────────────────┘
                      │ long-poll
┌─────────────────────▼──────────────────────────────────────────┐
│  app/channels/telegram.py     (BaseChannel impl)                │
│    - real: python-telegram-bot ApplicationBuilder + polling     │
│    - dry-run: log-only stub                                    │
│    - auth check (chat_id in allowed_chat_ids)                   │
│    - command-prefix interception (/help, /new, /status, /echo) │
└─────────────────────┬──────────────────────────────────────────┘
                      │ dispatch
┌─────────────────────▼──────────────────────────────────────────┐
│  app/channels/telegram_handler.py    (ChannelHandler fn)        │
│    telegram_handler(channel, sender, text) → str                │
│      1. session = TelegramSessionManager.get_or_create(sender)  │
│      2. agent = cached or new (with disk-loaded history)       │
│      3. result = await agent.run(text, context)                │
│      4. persist result.messages back to disk                   │
│      5. return result.output (or canned apology)                │
└─────────────────────┬──────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────────────────────────┐
│  app/channels/telegram_session.py   (persistence)               │
│    chat_id  ⇄  session_id  (atomic JSON write)                 │
│    ~/.gundam-halo/projects/telegram/                            │
│      ├── chat_map.json      # {"<chat_id>": "<session_id>", …}  │
│      └── sessions/<sid>/   # standard project session layout    │
└────────────────────────────────────────────────────────────────┘
```

#### Lifecycle wiring (`main.py`)

```python
from app.channels.telegram_handler import telegram_handler
manager = get_channel_manager()
manager.set_handler("telegram", telegram_handler)  # wire BEFORE start
await manager.start_all()                           # starts telegram if enabled
```

`ChannelManager.set_handler()` accepts the callback before
`start()`; the channel then routes every incoming message through it.
Without a handler, messages are received but produce no reply (the
old v0 behavior — now deprecated).

#### Configuration

```toml
[channels.telegram]
enabled = true               # set false to skip entirely
bot_token = ""               # GUNDAM_HALO_TG_TOKEN env var overrides
allowed_chat_ids = []         # empty = accept any chat (NOT recommended for prod)
command_prefix = "/"          # default
```

The `cmd_args` field in the `AGENT_TURN_START` event now carries
`channel="telegram"` so the dashboard can distinguish web vs. Telegram
turns in the live activity feed.

### Signal (v1: stub, v2: implement)

- Library: `pynostr`-style JSON-RPC, or call `signal-cli` daemon
- More setup than Telegram (need signal-cli installed)
- Same whitelist + command pattern

---

## 10. Per-project isolation — the key fix

This is **why Gundam Halo exists** (Hermes gets messy with too many projects).

### How it works

1. **Each project = isolated directory** under `~/.gundam-halo/projects/`
2. **Each session = one project** (you can't have two sessions in the same project — prevents context bleed)
3. **Memory is per-project** — `memory/short-term.jsonl`, `memory/long-term.db` (no shared global context)
4. **Tools are per-project** — `tools/<tool-call-id>.json` logs
5. **Files are per-project** — `files/` directory holds files referenced in this project only
6. **Archive on close** — when project archived, everything (memory, conversations, tools, files) goes to `archive/<project>/<snapshot>/`

### Switching projects

- Active project = the "current session"
- Switching via Telegram: `/switch <project>` → session state saved, new session loaded
- Switching via web UI: click project in TopBar → same
- Cost: ~1s save + load (acceptable)

### What is NOT shared between projects

- Conversation history
- Tool execution logs
- Memory embeddings
- File references
- Theme override (theme is per-user, not per-project, per locked decision #1)

### What IS shared

- User config (`config.toml`)
- Skills registry (per user)
- Mac control policies (per user)
- LLM connection

---

## 11. Security model

### Defense in depth (4 layers)

1. **Network** — Tailscale ACL only. Public internet is impossible.
2. **Channel** — Telegram/Signal whitelist of chat_ids / phone numbers.
3. **Policy** — Every Mac op goes through `mac/policy.py`. Default deny, explicit allow.
4. **Confirmation** — Dangerous ops (file write, shell, AppleScript, A11y) require inline confirmation from user.

### Threat model

| Threat | Mitigation |
|---|---|
| Attacker reaches gateway | Tailscale ACL (only user's devices) |
| Attacker compromises Telegram | Whitelist of chat_ids (only your chat) |
| Prompt injection in inbound text | `injection_scanner.py` on every inbound message |
| Agent runs dangerous command | `shell_allowlist` + confirmation |
| Agent writes outside project | `file_write_paths` policy |
| Agent exfiltrates via Telegram | Telegram channel only sends to whitelisted chat_ids |
| Compromised audit log | Append-only file, OS-level permissions (`chmod 600`) |
| LLM API key leak | Read from env, never stored in TOML/JSON |

### Non-negotiable security rules

- **No public internet exposure** — only Tailscale IP works
- **No shell without allowlist entry** — even the agent can't run `rm -rf /`
- **No file write outside `file_write_paths`** — even via legitimate-looking tool calls
- **No AppleScript without explicit user grant per session**
- **No Accessibility API without `a11y_enabled = true` AND per-session grant**
- **All secrets in env vars, never in config files**
- **Audit log is append-only and `chmod 600`**

---

## 12. Data flow example

**User (on phone, in Telegram)**: `/new fix-memory-leak`

```
[Telegram Bot]
    │  receives /new fix-memory-leak
    │  whitelists chat_id ✓
    │  routes to backend
    ▼
[FastAPI /api/sessions]
    │  projects/manager.create("fix-memory-leak")
    │  creates dir, project.toml
    │  session starts with agent_type=native_react
    ▼
[Session Manager]
    │  creates session instance
    │  registers with EventBus
    │  publishes session.start
    ▼
[Telegram response]
    │  "Project 'fix-memory-leak' created.
    │   Send messages to start working."
    ▼
[User]: read ~/workspace/jarvis/memory/store.py and find the leak
    │  routed as session message
    ▼
[Agent (native_react)]
    │  MiniMax API call → decides: read file
    │  emits tool_call_start
    │  calls mac/file_ops.read("~/workspace/jarvis/memory/store.py")
    ▼
[mac/policy.py]
    │  path allowed? YES (in file_read_paths)
    │  project active? YES
    │  audit log entry
    ▼
[mac/file_ops.py]
    │  reads file, returns content
    ▼
[Agent]
    │  MiniMax API call (with file content) → finds bug
    │  decides: write a fix
    │  emits tool_call_start
    │  calls mac/file_ops.write(...) — REQUIRES CONFIRMATION
    ▼
[Telegram response]
    │  Inline keyboard: "Agent wants to write to X. [Yes] [No]"
    ▼
[User taps Yes]
    │  routed back to session
    ▼
[mac/policy.py]
    │  path allowed? YES (in file_write_paths)
    │  audit log entry
    ▼
[mac/file_ops.py]
    │  writes file
    ▼
[Agent]
    │  "Found the leak, fixed in store.py.
    │   Want me to commit and push?"
    ▼
[User]: yes
    ▼
[Agent]
    │  calls mac/git.push()
    │  delegates to Mavis via bridge
    ▼
[Mavis]
    │  git diff → semantic commit msg
    │  git add, commit, push
    │  returns commit SHA
    ▼
[Telegram response]
    │  "Done! Pushed as commit abc123. View on GitHub: ..."
```

---

## 13. Open questions (for later)

These don't block implementation but are worth thinking about:

1. **Mavis bridge mechanism** — subprocess `mavis communication send` works but is heavyweight. Alternative: HTTP API (requires Mavis to expose one). Decide based on latency needs.
2. **Memory backend** — v1 uses SQLite + JSONL. v2 might add FAISS. Decide based on retrieval quality.
3. **Multi-device Tailscale** — Tailscale supports multiple devices. Should other devices (iPad?) be able to invoke the agent? If yes, Tailscale ACL needs more entries.
4. **Backup strategy** — `~/.gundam-halo/` is critical state. Should we auto-backup to iCloud Drive / external disk? (Maybe in v2.)
5. **First-run wizard** — v1 assumes user knows the config. v2 could have a `gundam-halo init` interactive wizard that walks through config.toml setup.

---

## 14. Changelog

| Date | Change |
|---|---|
| 2026-06-05 | Initial architecture spec. Backend modules, frontend modules, project workspace, API surface, Mac control pane, MiniMax integration, channel integration, per-project isolation, security model, data flow example. |
| 2026-06-07 | Added **§15 Voice + Live2D Interaction Layer** — voice input (ASR/VAD), TTS output, Live2D triggers. Borrowed ASR/VAD factory pattern from Open-LLM-VTuber, added NT-D / Unicorn styled response. Removed MCP scope from v1. |
| 2026-06-07 | **M2 shipped**: TTS engine (Microsoft Edge TTS, free / no API key) + sentence splitter (pysbd) + HaloResponder (emotion DSL → TTS stream + Live2D trigger). Voice WS now streams `tts.start` / `tts.audio` / `tts.end` frames. 157 tests pass. |
| 2026-06-07 | **M3-B3 Tray icon shipped**: Unicorn Gundam head in green Psycho-Frame. **Animated tray** — 88 frames @ 15 FPS extracted from a 6 s awakening video (calm → peak energy wings → back to calm), embedded in the binary via `include_dir!`, played by a dedicated `halo-tray-anim` thread that calls `tray.set_icon(...)` every 67 ms. Full tray menu (Open / Hide / New Chat / Settings / Quit) with macOS-style accelerators. Window close hides to tray; `--minimized` flag (used by autostart on login) starts hidden. Static bundle icons (PNG/ICNS/ICO) regenerated from frame 0. `tauri` crate now requires `tray-icon` + `image-png` features; added `image` + `include_dir` deps. Cargo build clean (48 MB debug binary, 6 MB up for embedded frames), smoke test passed. See §5.5.1. |
| 2026-06-07 | **M3-B4 Tool call → motion shipped**: `ToolMotionMapper` (`app/voice/live2d/tool_motion_mapper.py`) subscribes to `TOOL_CALL_START`/`TOOL_CALL_END` and publishes `LIVE2D_TOOL_TRIGGER` events with the appropriate `(expression, motion, emotion)` triple. Per-tool start/end frames for `file_read`, `file_write`, `shell_exec`, `spotlight_search`, `open_app`, `mavis_delegate`; failure always flinches (`ntd_damage`); unknown tools fall back to `ntd_focused`. Wired into FastAPI lifespan. Frontend `halo-live2d-bridge.ts` extended to subscribe to `live2d_tool_trigger` on the main `/ws` and route it through the same `dispatchLive2DTrigger` as the voice-emotion triggers — one pipeline, two sources. CSS Avatar and any future Live2D model pick it up with zero per-consumer changes. 18 new tests; 194 backend tests pass. See §15.8.1. |
| 2026-06-08 | **M3-B5 Peak-state icon refresh**: Tray icon and animation regenerated to match the "intense full Psycho-Frame awakening" design (white/gray Gundam head, two side V-fin antennas, green crystal core, explosive green energy burst, gold accents). `generate_tauri_icons.py` now accepts `--no-animation` for static-only refresh; both static bundle icons and the 88-frame tray animation now use the peak style. Animation is now a sustained awakening loop (energy pulses + particles flow + lightning flickers throughout, never returns to calm) rather than the previous calm→peak→calm ramp. Binary rebuilt; debug binary 52 MB (+4 MB for higher-detail frames), 0 cargo errors. 88 frames at 256², 15 FPS, ~10 MB embedded. |
| 2026-06-08 | **M3-B6 ActivityTicker tool_trigger feed**: Cockpit `ActivityTicker` now listens for `live2d_tool_trigger` events and renders each avatar reaction as a colored chip with the emotion icon + tool name + phase. Extracted emotion-to-display mapping into `frontend/src/lib/emotion-display.ts` (shared with future HUD overlays; `getEmotionDisplay` / `getPhaseIcon` are dependency-free and unit-testable). Emotion → color follows the cockpit palette: calm=muted, focused=cyan accent, awakening=pink psychoframe, alert=orange, damage=red, resolve/jubilant=green, stealth=secondary. Result: when the agent calls a tool, the ticker shows the sequence `🔧 file_read  ⚡ focused  ⚙ file_read ok  ○ calm` so the user reads "agent is doing X, feeling Y" in one glance. Tsc + vite build clean. |
| 2026-06-08 | **M3-B7 Runtime-tunable tray animation FPS**: Tray animation cadence is no longer a hard-coded const. Replaced `const FRAME_FPS = 15` with a process-wide `static ANIMATION_FPS: AtomicU32` (default 15, range [1, 60], clamped on write). The `halo-tray-anim` thread re-reads the FPS on every tick via `frame_interval_ms()` so speed changes take effect on the next frame — no thread restart, no icon glitch. Two Tauri commands: `set_animation_speed(fps) -> u32` (effective value post-clamp) and `get_animation_speed() -> u32`. Frontend wrapper `services/halo-tray-controls.ts` exposes `setAnimationSpeed` / `getAnimationSpeed` + `window.__haloTray` debug global for console testing. Documented recommended presets (8 battery saver, 15 default, 24 cinema). Cargo build clean, smoke test passes. |
| 2026-06-08 | **M3-B8 Settings panel UI for tray FPS**: Replaced the console-only debug global with a proper Settings UI. New "Tray Icon Animation" section in the existing **General** tab (`/settings`): live FPS read-out, 1–60 slider, 3 preset chips (Battery Saver 8 / Default 15 / Cinema 24), and a note that the value resets on app restart (persistence in v1.1). Slider fill is driven by a `--gundam-slider-fill` CSS custom property so the track lights up cyan to the current position. Slider/preset changes call the existing `set_animation_speed` Tauri command and toast the effective value. Tsc + vite build clean (CSS +2 KB, JS +3 KB). |
| 2026-06-08 | **M3-B9 Visual showpiece**: Generated project-wide visual identity from the peak-state Unicorn Gundam head source. Two wide compositions via `matrix_generate_image` (1280×320 README banner, 1280×640 Open Graph card) using the peak image as `first_frame`; square PFPs via Pillow resize from the 1024² master. Outputs: `docs/assets/{readme-banner-1280x320,og-card-1280x640,profile-pfp-800x800,profile-pfp-400x400}.png` and `.github/social-preview.png` (GitHub repo card convention). New `scripts/generate_visual_assets.py` re-runnable for asset regeneration. README rewritten with banner, visual identity table, accurate "Active development — v0.1" status. ~3 MB total asset size, no code impact, no test impact. |
| 2026-06-08 | **M4 Telegram channel integration shipped**: Telegram was the primary phone control surface (locked product decision) but the scaffold (`telegram.py`, `manager.py`, dry-run tests) wasn't wired to the agent — messages arrived but produced no reply. Three new pieces: (1) `app/channels/telegram_session.py` — thread-safe `TelegramSessionManager` mapping `chat_id → session_id` with atomic JSON persistence (`~/.gundam-halo/projects/telegram/chat_map.json`); (2) `app/channels/telegram_handler.py` — the `telegram_handler` channel callback that creates/resumes an agent for the chat and persists conversation history; (3) `app/channels/telegram.py` — command-prefix interception (`/help`, `/new`, `/status`, `/echo`) before agent dispatch, with unknown commands falling through to the agent. `ChannelManager.set_handler(channel_id, handler)` added so `main.py` can wire callbacks before `start()`. 26 new tests (`tests/channels/test_telegram_session.py`): session CRUD/persistence/corruption recovery, command parsing, command-vs-handler routing order, manager wiring. **220 backend tests pass** (was 194). See §9. |
| 2026-06-09 | **M6 Dashboard secrets management shipped**: Previously the only way to set the MiniMax API key or Telegram bot token was to paste into a `.env` file or environment variable — a flow that doesn't match "local project with secrets managed in the UI". M6 adds a full dashboard-driven secret store. New `app/core/secrets_store.py` — `SecretStore` singleton with in-memory override map, atomic `0600`-permissioned `~/.gundam-halo/.env` write, mirror into `os.environ`, and config-cache invalidation so the next LLM / Telegram request picks up new values without a server restart. New `app/api/secrets.py` — `GET /api/secrets` (returns only `{configured, source}` masks, never values), `POST /api/secrets` (set one or many, idempotent + atomic), `DELETE /api/secrets/{name}` and `POST /api/secrets/clear` (drop). 26 new tests covering: 0600 permissions, unknown-key rejection, no-leak-into-log, no-value-in-response, atomic write (no `.env.*` leftover), reload from existing file, cache invalidation. `main.py` `create_app()` now idempotent on tool registration (was a test-isolation bug). New Settings tab "Secrets" in `routes/settings.tsx` with two password inputs (MiniMax + Telegram), secure input attrs (`autocomplete="off"`, `data-1p-ignore`, `data-bwignore`), Save / Clear / Refresh, sonner toasts on success. **246 backend tests pass** (was 220). Tsc + vite build clean. See §5.5.1.1 below. |
| 2026-06-10 | **M7 — Live feel + web tools + user memory shipped in 3 phases**. The cockpit is now visibly "alive" between turns, can answer real-world questions, and remembers per-user context across sessions. **Phase 0.1 (avatar idle)**: 4 pure-CSS keyframe animations on the CSS Avatar when emotion is `calm` — `avatar-idle-breath` (4.2 s scale + Y), `avatar-idle-scan` (7 s drift), `avatar-idle-blink` (5.5 s double-blink), `avatar-idle-glow` (3 s opacity). Zero JS, zero server coupling; auto-paused when the avatar switches to an active emotion. **Phase 0.2 (voice button states)**: `voice-mic` ambient breath baseline; `--listening` press-scale + 2× ring expand; `--thinking` shimmer sweep; `--speaking` audio-bar. Wired into `VoicePanel.tsx` via the WS state machine — no extra props. **Phase 0.3 (live log stream)**: `BackendLogHandler` (`logging.Handler`) publishes `INFO+` log lines to the event bus as `BACKEND_LOG` events; `ActivityTicker` learns a new `backend_log` case that renders the level + source + message. Auto-broadcasts via the main `/ws`, so all open dashboards see the agent thinking in real time. **Phase 1.1–1.5 (web tools)**: `WebFetchTool` (httpx-based, async, 64 KB cap, http(s)-only, configurable timeout/max_chars) and `WeatherTool` (wttr.in, no API key, structured temp/feels/humidity/wind/visibility/pressure/sunrise/sunset) — both registered in `default_tools()`; 17 respx-mocked unit tests. **Phase 1.6–1.7 (frontend chips)**: The existing `ActivityTicker` already renders `tool_call_start`/`tool_call_end` for any tool name including `web_fetch` / `weather`; no frontend work needed. **Phase 2.1 (user identity)**: `channels.telegram.display_names[chat_id] = "Ken"` in `config.toml`; new `app/channels/identity.py` with `ChannelIdentity` dataclass and `resolve_telegram_identity_cached()` (priority: config > group title > first_name > chat_id). `AgentContext` extended with `user_display_name`; `telegram_handler` resolves the identity at session start and threads it through. **Phase 2.2–2.3 (memory store + tools)**: New `app/memory/user_memory.py` — file-backed per-user key/value store at `~/.gundam-halo/memory/users/<key>/<slug>.md` with `_index.json` manifest, `flock`-serialized writes, 8 KB value cap, slug-normalized keys, markdown export. `MemoryReadTool` and `MemoryWriteTool` are scoped to the current user (resolved from `AgentContext.user_display_name`). Native React agent threads `display_name` and `transport_id` into tool kwargs. **Phase 2.4 (auto-recall)**: New `app/agents/system_prompt.py` `build_system_prompt()` augments the base system prompt with a "## Who you're talking to" block (display name + channel) and a "## What you remember about this user" block (up to 25 memory entries, sorted by recency). Hooked into both `NativeReActAgent.run()` and `SimpleAgent.run()`. **Phase 2.5 (dashboard viewer)**: New read-only `Memory` tab in Settings — user list, expandable per-user panel, entry cards with key/value/timestamps, "Delete" button for cleanup. 4 new API endpoints: `GET /api/memory`, `GET /api/memory/{user}`, `GET /api/memory/{user}/{key}`, `DELETE /api/memory/{user}/{key}`. **314 backend tests pass** (was 246, +68). 7/7 smoke checks, 30/30 telegram dry-run. Tsc + vite build clean (JS 388 KB, CSS 52 KB). |

---

## 15. Voice + Live2D Interaction Layer

This section is **additive** — it does not change any decision in §1–§14. It defines the voice input / TTS output / Live2D avatar trigger layer that makes Gundam Halo feel like a cockpit companion, not a CLI bot.

**Reference implementation borrowed from**: [`Open-LLM-VTuber`](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) (Apache 2.0 / MIT for code, Live2D assets have separate license). We **borrow the factory pattern and module structure** (vad/, asr/, tts/, live2d/) but write fresh code, and we **drop** Live2D's standalone web/desktop distribution — our frontend is Tauri 2.

### 15.1 Design principles

1. **Voice is one input channel among many** — not a replacement for text. Tauri app can mix voice + text + Telegram message seamlessly. All three end up as `Message(role=user, content=...)` to the agent.
2. **Modular engine factories** — ASR / TTS / VAD each have a `*_factory.py` that picks the backend from `config.toml`. v1 ships one backend per slot; the factory makes v2+ pluggable without touching call sites.
3. **Live2D is decoupled from voice** — the agent never directly sends "play this motion". A `HaloResponder` layer translates agent outputs (text + emotion tag) into Live2D triggers. This keeps LLM prompts simple.
4. **Apple Silicon first** — local Whisper on Metal is fast enough; no cloud ASR needed. Document the Intel-Mac fallback path anyway.
5. **No MCP in v1** — explicitly removed from scope. Re-evaluate post-v1.
6. **MCP is out for v1** — see §15.9 for why and what to revisit.

### 15.2 Updated high-level architecture

```
┌─────────────────────────────────────────────────────────────┐
│  PRESENTATION                                               │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────┐      │
│  │ Tauri app    │  │ Telegram    │  │ (future) Signal│      │
│  │ - mic stream │  │ Bot         │  │                │      │
│  │ - Live2D     │  │             │  │                │      │
│  │ - text input │  │             │  │                │      │
│  └──────┬───────┘  └──────┬──────┘  └────────┬───────┘      │
│         │ WS (audio+txt)  │ HTTPS           │              │
└─────────┼─────────────────┼────────────────────┼─────────────┘
          │                 │                    │
          ▼                 ▼                    ▼
┌─────────────────────────────────────────────────────────────┐
│  BACKEND (FastAPI)                                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Voice Layer (NEW — see §15.4)                        │   │
│  │   vad/  →  asr/  →  message  →  agent               │   │
│  │ Response path: agent → halo_responder → tts + live2d │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ API layer (REST + WebSocket)                         │   │
│  │   channels/  mac/  agents/  projects/  tools/  ...   │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Core (registry / events / types)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────────┘
                          │ HTTPS
                          ▼
                ┌──────────────────────┐
                │  MiniMax API         │
                │  (LLM brain)         │
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │  Mac system          │
                │  (file / shell /     │
                │  AppleScript / A11y) │
                └──────────────────────┘
```

### 15.3 New module layout (additive to §3)

```
backend/app/
├── voice/                       # NEW — voice input pipeline
│   ├── __init__.py
│   ├── pipeline.py              # VAD → ASR → message orchestration
│   ├── vad/
│   │   ├── vad_interface.py     # VAD interface (mirrors Open-LLM-VTuber)
│   │   ├── vad_factory.py
│   │   └── silero_vad.py        # v1: Silero VAD
│   ├── asr/
│   │   ├── asr_interface.py
│   │   ├── asr_factory.py
│   │   └── whisper_local.py     # v1: local Whisper (Metal/CPU)
│   ├── tts/
│   │   ├── tts_interface.py
│   │   ├── tts_factory.py
│   │   └── edge_tts.py          # v1: Edge TTS (free, no key)
│   └── live2d/                  # NEW — Live2D trigger layer
│       ├── live2d_interface.py
│       ├── live2d_factory.py
│       ├── live2d_model.py      # model metadata loader
│       └── ntd_responder.py     # NT-D / Unicorn emotion mapping (v1 theme)
├── halo_responder/              # NEW — agent output → (tts + live2d + text)
│   ├── __init__.py
│   ├── halo_responder.py        # HaloResponder class
│   ├── emotion_parser.py        # parses [EMO:awakening] style tags
│   └── tts_streamer.py          # streams TTS audio via WS to client
└── (existing modules unchanged)
```

### 15.4 Voice input pipeline

Mirrors Open-LLM-VTuber's pipeline with adaptations for Tauri client and our security model.

**Flow per turn**:

```
Tauri mic (WebAudio PCM 16kHz mono)
  → WS binary frame (chunked, ~250ms each)
  → vad/SileroVAD (frame-level speech probability)
  → trigger when prob > 0.5 for N consecutive frames → "speech_start"
  → buffer audio chunks
  → trigger when prob < 0.3 for M frames after start → "speech_end"
  → asr/WhisperLocal.transcribe(buffer)
  → produce Message(role=user, content=text)
  → routed to active session (same path as Telegram text)
  → Session Manager
  → Agent loop (MiniMax API)
  → response: text + [EMO:xxx] tags
  → halo_responder:
      → text → tts/EdgeTTS.synthesize() → audio bytes → WS to client
      → [EMO:xxx] → live2d/responder.trigger(motion) → WS to client
  → mac/tool_call? → execute → result back to agent → loop
  → final response sent to all active channels (Tauri + Telegram)
```

**Key choices**:

- **Chunk size**: 250ms audio frames. Trade-off: smaller = lower latency, larger = better VAD accuracy. Start with 250ms, tune later.
- **VAD**: Silero VAD v5. ~2MB ONNX, runs on CPU at <1ms per frame. We bundle the model in `backend/models/silero_vad.onnx`.
- **ASR**: `openai-whisper` (Python package, NOT the `whisper.cpp` binary). Use `tiny` or `base` model for v1. Apple Silicon uses PyTorch Metal backend automatically.
- **Streaming**: TTS synthesis is per-sentence (use `pysbd` to split). Don't wait for full LLM response — first sentence triggers TTS immediately, overlap with LLM streaming.

### 15.5 ASR engine contract

```python
# voice/asr/asr_interface.py
from abc import ABC, abstractmethod

class ASRInterface(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, sample_rate: int = 16000) -> str:
        """Transcribe a complete audio buffer to text.
        
        Args:
            audio: PCM 16-bit mono audio bytes
            sample_rate: 16000 expected for v1
            
        Returns:
            Transcribed text (whitespace-trimmed, no punctuation normalized)
            
        Raises:
            ASRError: on backend failure
        """
        ...
    
    @abstractmethod
    async def warmup(self) -> None:
        """Load model into memory. Called once at startup."""
        ...
```

**v1 implementations**:
- `WhisperLocalASR(ASRInterface)` — uses `openai-whisper` package. Model size from `config.toml [voice.asr] model_size` (default `"base"`).

**Future candidates** (interface ready, not implemented):
- `WhisperCppASR` — faster, GPU accelerated, but binary dep
- `FunASR` — better for Chinese
- `GroqWhisperASR` — cloud fallback

### 15.6 VAD engine contract

```python
# voice/vad/vad_interface.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class VADEvent:
    is_speech: bool
    probability: float  # 0.0 - 1.0
    timestamp_ms: int

class VADInterface(ABC):
    @abstractmethod
    def process_frame(self, audio_frame: bytes, sample_rate: int = 16000) -> VADEvent:
        """Process one frame (~250ms), return speech detection event."""
        ...
    
    @abstractmethod
    async def warmup(self) -> None:
        """Load ONNX model into memory."""
        ...
```

**v1 implementation**: `SileroVAD(VADInterface)` — borrows directly from Open-LLM-VTuber's implementation pattern (same ONNX model, same threshold defaults: 0.5 start, 0.3 end, 250ms min speech, 100ms min silence).

### 15.7 TTS engine contract

```python
# voice/tts/tts_interface.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class TTSResult:
    audio_bytes: bytes
    format: str          # "mp3" | "wav" | "opus"
    sample_rate: int
    duration_ms: int

class TTSInterface(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str | None = None) -> TTSResult:
        """Synthesize one chunk of text to audio.
        
        Args:
            text: input text (typically one sentence)
            voice: voice ID (provider-specific)
            
        Returns:
            TTSResult with audio bytes
        """
        ...
```

**v1 implementation**: `EdgeTTS(TTSInterface)` — `edge-tts` Python package, no API key needed, supports zh-HK / zh-CN / en / ja. Voice from `config.toml [voice.tts] voice` (default `"zh-HK-HiuMaanNeural"` for Cantonese-leaning feel, or `"zh-CN-XiaoxiaoNeural"` for standard).

### 15.8 Live2D trigger layer

Decoupled from LLM prompt. The LLM never speaks Live2D's language. Instead, the LLM is prompted to output emotion tags in a stable mini-DSL, and `HaloResponder` translates them.

**Emotion DSL** (final form, locked):

```
[EMO:calm]      [EMO:focused]    [EMO:awakening]   [EMO:alert]
[EMO:damage]    [EMO:resolve]    [EMO:jubilant]    [EMO:stealth]
```

Each maps to: expression (face) + motion (body) + voice pacing hint.

```python
# halo_responder/ntd_responder.py (sketch)
EMOTION_MAP = {
    "calm":      {"expr": "ntd_calm",      "motion": "idle",     "tts_rate": 1.0},
    "focused":   {"expr": "ntd_focused",   "motion": "lean_in",  "tts_rate": 0.95},
    "awakening": {"expr": "ntd_psychoframe","motion": "awaken",  "tts_rate": 1.05},  # 精神感應
    "alert":     {"expr": "ntd_alert",     "motion": "scan",     "tts_rate": 1.1},
    "damage":    {"expr": "ntd_damage",    "motion": "flinch",   "tts_rate": 0.9},
    "resolve":   {"expr": "ntd_resolve",   "motion": "stand",    "tts_rate": 1.0},
    "jubilant":  {"expr": "ntd_jubilant",  "motion": "victory",  "tts_rate": 1.1},
    "stealth":   {"expr": "ntd_stealth",   "motion": "vanish",   "tts_rate": 0.85},
}

class NTDResponder:
    def __init__(self, live2d: Live2DInterface, tts: TTSInterface):
        self.live2d = live2d
        self.tts = tts
    
    async def respond(self, agent_text: str, emotions: list[str]) -> TTSResult:
        emo = emotions[0] if emotions else "calm"
        cfg = EMOTION_MAP.get(emo, EMOTION_MAP["calm"])
        await self.live2d.trigger(cfg["expr"], cfg["motion"])
        return await self.tts.synthesize(agent_text, voice=..., rate=cfg["tts_rate"])
```

**Theme coupling**: `NTDResponder` is the v1 default. v2 will add `SeedFreedomResponder`, `CrossboneResponder`, etc. — same interface, different emotion mappings and motion assets. Theme selection stays per-user (locked decision §13).

**Live2D model**: v1 uses one bundled model from the gundam-assets library (`/Users/kencheng/hermes-workspace/assets/gundam-assets/`). User supplies their own `.model3.json` via config in v2.

#### 15.8.1 Tool call → motion (M3-B4)

The LLM-emotion pipeline above only fires when the agent is **speaking**.
For the cockpit to feel alive in between turns, the avatar also reacts
to **tool calls** — the agent reading a file leans in, opening an app
does a small victory, and a failing tool makes it flinch.

**Architecture**: a passive `ToolMotionMapper` subscribes to the
`EventBus` and translates every `TOOL_CALL_START` / `TOOL_CALL_END` into
a `LIVE2D_TOOL_TRIGGER` event. The main `/ws` channel broadcasts it to
every connected client; the frontend's `halo-live2d-bridge.ts`
listens for both `live2d.trigger` (voice WS) and `live2d_tool_trigger`
(main WS) and routes them through the same `dispatchLive2DTrigger` —
so the CSS Avatar, the real Live2D model, and any future consumer all
see the same trigger shape.

**Mapping table** (`app/voice/live2d/tool_motion_mapper.py`):

| Tool | Start frame | End frame (ok) | End frame (fail) |
|---|---|---|---|
| `file_read` | ntd_focused · lean_in · focused | ntd_calm · idle · calm | ntd_damage · flinch · damage |
| `file_write` | ntd_resolve · stand · resolve | ntd_calm · idle · calm | ntd_damage · flinch · damage |
| `shell_exec` | ntd_alert · scan · alert | ntd_calm · idle · calm | ntd_damage · flinch · damage |
| `spotlight_search` | ntd_alert · scan · alert | ntd_calm · idle · calm | ntd_damage · flinch · damage |
| `open_app` | ntd_jubilant · victory · jubilant | ntd_calm · idle · calm | ntd_damage · flinch · damage |
| `mavis_delegate` | ntd_psychoframe · awaken · awakening | ntd_calm · idle · calm | ntd_damage · flinch · damage |
| _unknown_ | ntd_focused · lean_in · focused | ntd_calm · idle · calm | ntd_damage · flinch · damage |

The failure frame is **always** `ntd_damage · flinch · damage`
regardless of the tool, so the avatar visibly flinches on any error.
The fallback row covers new custom tools added to `ToolRegistry` without
needing to update this table.

**Wire format** (broadcast on the main `/ws` channel):

```json
{
  "type": "live2d_tool_trigger",
  "ts": 1718...,
  "data": {
    "source": "tool",
    "tool": "file_read",
    "phase": "start",
    "call_id": "call-7",
    "session_id": "sess-42",
    "project": "...",
    "expression": "ntd_focused",
    "motion": "lean_in",
    "emotion": "focused"
  }
}
```

The same triple (`expression`, `motion`, `emotion`) is what the voice
WS's `live2d.trigger` frame carries, so a single dispatch function on
the frontend handles both sources.

**Adding a new tool**: drop a row in `TOOL_MOTION_MAP`. No other
backend code change needed. No frontend change. The avatar picks it up
the next time the tool runs.

### 15.9 WebSocket message protocol (additions)

Existing §7.2 has the base WS protocol. New message types for voice:

**Client → Server** (binary frames are audio PCM):

```typescript
// Audio streaming
{ "type": "voice.start",   "session_id": "..." }                     // begin a turn
{ "type": "voice.audio",   "session_id": "...", "seq": 0 }            // binary frame follows
// (binary frame)
{ "type": "voice.end",     "session_id": "...", "seq": 0 }            // end audio, trigger ASR
{ "type": "voice.cancel",  "session_id": "..." }                      // user cancels mid-utterance

// Manual control (optional v1)
{ "type": "voice.text",    "session_id": "...", "text": "open Safari" }  // text-only turn (bypass ASR)
```

**Server → Client**:

```typescript
// VAD feedback (low-frequency UI hint)
{ "type": "vad.state",     "session_id": "...", "is_speech": true,  "prob": 0.87 }

// ASR result
{ "type": "asr.result",    "session_id": "...", "text": "open Safari", "duration_ms": 1240 }

// Agent events (existing types)
{ "type": "agent.thinking" }
{ "type": "agent.message", "text": "Opening Safari.", "emotions": ["calm"], "is_final": true }
{ "type": "agent.tool_call", "tool": "open_app", "args": { "app": "Safari" } }

// TTS audio stream
{ "type": "tts.start",     "session_id": "...", "voice": "zh-HK-HiuMaanNeural" }
{ "type": "tts.audio",     "session_id": "...", "seq": 0 }            // binary frame follows
{ "type": "tts.end",       "session_id": "..." }

// Live2D trigger (independent of TTS — can fire for tool events too)
{ "type": "live2d.trigger","session_id": "...", "expression": "ntd_focused", "motion": "lean_in" }
```

**Audio frame format**: PCM 16-bit signed little-endian, 16kHz mono, 250ms = 8000 bytes per frame.

### 15.10 Configuration additions

Append to `config.toml`:

```toml
[voice]
enabled = true                          # set false to disable voice layer entirely
vad = "silero"                          # only "silero" in v1
asr = "whisper_local"                   # only "whisper_local" in v1
tts = "edge"                            # only "edge" in v1
sample_rate = 16000
frame_duration_ms = 250

[voice.vad]
model_path = "~/.gundam-halo/models/silero_vad.onnx"  # auto-downloaded on first run
speech_threshold_start = 0.5
speech_threshold_end = 0.3
min_speech_ms = 250
min_silence_ms = 700                    # end-of-utterance detection

[voice.asr]
model_size = "base"                     # tiny|base|small|medium|large
language = "auto"                       # auto|en|zh|yue|ja|...
device = "auto"                         # auto|cpu|cuda|mps
compute_type = "auto"                   # auto|int8|float16|float32

[voice.tts]
voice = "zh-HK-HiuMaanNeural"           # default Cantonese-leaning
rate = "+0%"
pitch = "+0Hz"
volume = "+0%"

[voice.live2d]
enabled = true
theme = "ntd"                           # v1: only "ntd"
model_path = "~/.gundam-halo/models/live2d/unicorn/"  # NT-D / Unicorn bundled
default_emotion = "calm"
```

**Intel Mac fallback** (not v1, but documented for v2): `device = "cpu"`, `compute_type = "int8"`, `model_size = "tiny"`. Cloud ASR (Groq Whisper) as a switchable fallback.

### 15.11 Agent system prompt additions

The agent must learn to emit emotion tags. Append to base system prompt:

```
When responding, prefix your message with one emotion tag from this set
when the emotional state is clear: [EMO:calm] [EMO:focused] [EMO:awakening]
[EMO:alert] [EMO:damage] [EMO:resolve] [EMO:jubilant] [EMO:stealth]

Default to [EMO:calm] for routine responses. Use [EMO:awakening] when
you detect something interesting / important. Use [EMO:alert] for warnings.

Only one emotion tag per turn. Place it on the first line of your response.
```

**Why this works**: Stable, parseable, model-friendly. Llama 3.3 / Claude / GPT-4 all follow this pattern well with >95% accuracy when given examples. We add 3 in-context examples in the system prompt for v1.

### 15.12 Security considerations (additive to §11)

- **Voice input goes through the same `injection_scanner.py`** as Telegram text. The ASR output is just another inbound text. No new attack surface.
- **No audio leaves the Mac.** All ASR is local Whisper. No audio uploaded.
- **TTS is outbound to Edge TTS service** (Microsoft's free endpoint). Text only, no PII normally. If user is paranoid, allow `tts = "pyttsx3"` (offline) in v2.
- **Voice is disabled when `a11y_enabled = false`** to prevent the agent from acting on whispered / accidental audio.
- **Confirmation flow** for dangerous Mac ops still applies — voice input doesn't bypass the confirm step.

### 15.13 Performance budget (Apple Silicon M-series)

| Stage | Latency target | Notes |
|---|---|---|
| VAD per frame | <5ms | Silero ONNX, CPU |
| ASR for 3s utterance | <1.5s | Whisper base, MPS backend |
| LLM first token | <800ms | MiniMax API, streaming |
| TTS first sentence | <600ms | Edge TTS, network-dependent |
| Live2D trigger | <50ms | local motion play |
| **End-to-end (utterance end → first audio out)** | **<3s** | Target |

If end-to-end exceeds 5s, user feels the delay. Track this metric from v1.

### 15.14 Roadmap (voice layer, in order)

1. **M1 (1 wk)**: Voice pipeline skeleton — VAD + ASR + LLM, no TTS, no Live2D. Text response on Tauri UI. Validates the audio flow.
2. **M2 (1 wk)**: Add TTS — Edge TTS, sentence-level streaming, audio plays in Tauri app. Voice feels responsive.
3. **M3 (1 wk)**: Add Live2D — bundle one NT-D / Unicorn model, wire up emotion DSL, NTDResponder. Theme switcher works.
4. **M4 (1 wk)**: NT-D polish — emotion DSL in agent system prompt, motion triggers for tool calls (e.g., "scanning" motion during mac/spotlight.search). Cockpit feel complete.
5. **M5+ (post-v1)**: Voice interruption (barge-in), per-user voice clone (GPT-SoVITS), theme switcher UI.

### 15.15 What we did NOT take from Open-LLM-VTuber

- ❌ Their web/desktop client distribution (we use Tauri)
- ❌ Their conf.yaml multi-character system (we use single user / per-project)
- ❌ Their Live2D rendering pipeline (we use pixi-live2d-display in the Tauri webview)
- ❌ Their agent abstractions (basic_memory, hume_ai, letta, mem0) — we use MiniMax-native ReAct
- ❌ MCP integration
- ❌ Group conversation mode

### 15.16 Open questions for v1 (voice)

1. **Wake word?** Should Halo always listen, or require a wake word (e.g., "Halo")? v1: always-on with VAD (manual PTT button as fallback in Tauri UI). Wake word is a v2 feature.
2. **Push-to-talk vs always-on?** Both supported in v1 — Tauri app has a mic toggle button. Default is push-to-talk (safer for accidental audio).
3. **Voice interruption (barge-in)?** TTS is playing, user starts speaking again — should TTS stop? v1: yes, via VAD detection of new speech during TTS playback. v2: refine cancellation logic.
4. **Multi-language code-switching?** User mixes Cantonese + English + Mandarin. v1: ASR `language = "auto"`, TTS voice picks based on detected language per sentence. TTS translation feature is post-v1.
5. **Audio storage?** Do we keep recordings of user voice? **No.** v1: audio is ephemeral, dropped after ASR. No voice recordings persisted. (Privacy stance — same as Hermes.)


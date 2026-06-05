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
- Tray icon: persistent, click to focus
- Global hotkey: `⌥Space` (configurable) → focus dashboard
- Window state persistence (size/position)
- No separate floating panel in v1

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

### Telegram

- Library: `python-telegram-bot` v22+
- Bot token from `GUNDAM_HALO_TG_TOKEN` env var
- Whitelist: only allowed `chat_ids` (your chat ID)
- Commands:
  - `/new <project>` — create new project session
  - `/switch <project>` — switch active session
  - `/list` — list projects
  - `/status` — current project status
  - `/code <task>` — explicitly invoke coding sub-agent (Mavis)
  - `/archive` — archive current project
  - plain text → routed as message to active session
- Confirmation flow: dangerous actions (file write, shell, AppleScript, A11y) require user to tap "Yes" button on the inline keyboard

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

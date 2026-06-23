# FEATURE-SPEC-SPRINT36.md — Workspace markdown pattern + SKILL.md metadata

**Status:** shipped 2026-06-23 (v0.1.6).
**Owner:** Unicorn (Mavis).
**Source-of-truth:** `app/core/agent_context.py`,
`app/core/skill_metadata.py`, `app/data/workspace/*.md`,
`app/data/skills/<name>/SKILL.md`.

## Origin — OpenClaw fork study

The user pointed me at their `~/.openclaw/` install (an
OpenClaw v2026.5.31 data directory + the bundled
`/Users/kencheng/openclaw/dist/extensions/` source tree) and
asked how to learn from OpenClaw's skill / plugin /
agent-context patterns. After reading the 8-file
`~/.openclaw/workspace/` markdown structure
(`AGENTS.md` / `SOUL.md` / `USER.md` / `IDENTITY.md` /
`TOOLS.md` / `HEARTBEAT.md` / `BOOTSTRAP.md` / `MEMORY.md`)
and the `extensions/<plugin>/skills/<skill>/SKILL.md`
contract, I recommended three tiers of fork; the user
approved Tier 1 + Tier 2 (this sprint); Tier 3 is deferred.

Gundam Halo's deployment is single-user / Mac-only /
Tauri + dashboard (per the user profile's
"control surface priority"), so the OpenClaw surface is
trimmed — no multi-channel gateway, no plugin marketplace,
no marketplace install/refresh — but the **pattern** of
markdown-driven agent context + markdown-enriched tool
descriptions transfers cleanly.

## Tier 1 — Workspace markdown loader (shipped)

### Goal

Let the user edit the agent's personality, behaviour
contract, and operating environment by editing plain
markdown files in `~/.gundam-halo/workspace/`, instead of
editing Python source code in `app/agents/system_prompt.py`.

### File layout (after `ensure_workspace_seeded` first run)

```
~/.gundam-halo/workspace/
├── AGENTS.md      # Behaviour contract (master rules)
├── SOUL.md        # Personality + boundaries
├── USER.md        # Human profile (name/timezone/projects)
├── IDENTITY.md    # Agent's name/creature/vibe/emoji/avatar
├── TOOLS.md       # Local env notes (camera/SSH/voice)
├── HEARTBEAT.md   # Periodic checklist (empty = skip)
└── BOOTSTRAP.md   # One-shot first-run wizard (deleted after first turn)
```

Starter files ship in `backend/app/data/workspace/` and
are auto-copied to the user's home on first load. Existing
files are NEVER overwritten (mirrors OpenClaw's
seeding behaviour for `AGENTS.md`).

### Loader contract — `app/core/agent_context.py`

```python
def load_workspace(home: Path, *, force: bool = False) -> List[WorkspaceDoc]
def format_for_prompt(docs: List[WorkspaceDoc], *, max_chars: int = 12000) -> str
def ensure_workspace_seeded(home: Path) -> bool
def has_bootstrap(docs: List[WorkspaceDoc]) -> bool
def reset_cache() -> None  # test-only
```

Properties:

- **Order is stable**: docs come back in `PROMPT_ORDER`
  (`AGENTS.md` → `SOUL.md` → `USER.md` → `IDENTITY.md`
  → `TOOLS.md` → `HEARTBEAT.md`), then `BOOTSTRAP.md` is
  appended last (the prompt formatter skips it).
- **Freshness via mtime**: module-level cache keyed on
  `home` + `max(stat.st_mtime for p in workspace/*.md)`.
  User edits are picked up on the next turn without a
  backend restart.
- **Truncation cap**: `format_for_prompt(max_chars=12000)`
  emits a `_... truncated at 12000 chars; edit workspace/<file> to keep full content_`
  marker so the LLM still knows more exists.
- **Failure modes are soft**: missing workspace dir
  triggers `ensure_workspace_seeded` (copies starter set);
  unreadable file → skip with warning; cache survives
  across calls within one process.

### Wiring — `app/agents/system_prompt.py`

The runtime's `build_system_prompt(base_prompt, context)`
now appends the workspace markdown as the **first**
extra block (before the identity block and the memory
recall block). Stable order across turns:

1. Workspace markdown (`## AGENTS.md` ... `## HEARTBEAT.md`)
2. `## Who you're talking to` (only if `user_display_name`)
3. `## What you remember about this user` (only if
   memory entries exist)

The contract changed: `build_system_prompt("base",
context=ctx)` previously returned `"base"` when the context
had no display name; now it returns
`"base\n\n---\n\n## AGENTS.md\n..."` regardless. Two
existing tests in `tests/memory/test_user_memory.py`
were updated to reflect this (the workspace is agent-wide
context, not per-turn context).

### Why Tier 1 over a class-based approach

A pure-Python dataclass for "agent personality" would force
the user to write Python to tune Unicorn. A 200-line
markdown file lets the user write 200 lines of markdown
to tune Unicorn — same effort, zero compile cycle. The
runtime cache + mtime check make this as fast as a
class-based config (one filesystem `stat()` per turn).

## Tier 2 — SKILL.md metadata loader (shipped)

### Goal

Give every registered tool a rich, user-editable
OpenAPI description. Today the description is a 1-3
sentence class attribute (e.g. `file_read`'s description
is 154 chars). With SKILL.md enrichment, the LLM sees the
frontmatter description + the body (operating loop +
examples + red lines + recovery patterns) — typically
5-15x richer context per tool.

### File layout (after `ensure_skill_seeded` first run)

```
~/.gundam-halo/skills/
├── file_read/SKILL.md
├── file_write/SKILL.md
├── shell_exec/SKILL.md
├── ... (22 total, one per registered tool)
```

Starter files ship in `backend/app/data/skills/<name>/SKILL.md`
and are auto-copied on first load. Existing files are
never overwritten.

### SKILL.md frontmatter (OpenClaw pattern)

```yaml
---
name: file_read
description: Read the contents of a text file from disk. Use when you need to inspect a file's contents.
user-invocable: true
---

# file_read

Read a text file's contents. Policy-gated by ...

## Operating Loop
...

## Examples
...

## Red Lines
...

## Recovery
...
```

The loader (`parse_skill_md`) supports only `key: value`
lines in the frontmatter (no nested keys, no lists, no
quoting). Anything more complex is a sign the SKILL.md
author should simplify; the loader warns and continues.

`user-invocable` is currently informational only (Tier 2
just stores it; future UI work may surface a "user-
invocable" badge in the cockpit).

### Loader contract — `app/core/skill_metadata.py`

```python
def parse_skill_md(text: str, *, path: Optional[Path] = None) -> SkillMetadata
def load_skill(home: Path, tool_name: str) -> Optional[SkillMetadata]
def load_all_skills(home: Path) -> Dict[str, SkillMetadata]
def preload_cache(home: Path) -> None
def ensure_skill_seeded(home: Path, tool_names: List[str]) -> int
def reset_cache() -> None  # test-only
def _get_skill_for_spec(tool_name: str, fallback_description: str) -> str
```

Properties:

- **Same freshness pattern** as Tier 1: mtime-keyed cache.
- **`enriched_description`**: the frontmatter description
  + body, joined with `\n\n` separator. The body is the
  raw markdown between the closing `---` and EOF.
- **`to_spec()` enrichment**: when the cache has an entry
  for a tool name, `_get_skill_for_spec` returns the
  enriched description; otherwise returns the
  `fallback_description` unchanged. The fallback is
  additive only — tools without a SKILL.md behave exactly
  as before.

### Wiring — `app/tools/_stubs.py` + `app/tools/builder.py`

`BaseTool.to_spec()` now lazy-imports
`app.core.skill_metadata._get_skill_for_spec` and uses it
to replace the `function.description` field. The cache is
populated by `default_tools()` at agent-init time
(`preload_cache(cfg.home)` + `ensure_skill_seeded(...)`),
so per-turn `to_spec()` calls are O(1).

### Measured impact (file_read as a representative case)

- Class-level description: **154 chars**
- After SKILL.md enrichment: **2149 chars** (frontmatter
  description + 6-section body: Operating Loop, Examples,
  Red Lines, Recovery, plus 3 paragraphs of context)
- 22 tools enriched = the LLM gets ~1500 chars × 22 ≈
  33 KB of rich tool context per turn (downstream token
  cost scales with actual tool count in the agent's
  visible spec list, not all 22)

## Tier 3 — DEFERRED

### What Tier 3 would have been

A formal `app/plugins/` registry with an OpenClaw-style
manifest loader:

```
~/.gundam-halo/plugins/<name>/
├── openclaw.plugin.json    # {id, name, description, contracts, ...}
└── src/<name>.py           # plugin impl
```

Plus an `app.core.plugins.PluginRegistry` (decorator-
based, mirroring `ToolRegistry`) that auto-discovers
plugins from `app/plugins/<name>/__init__.py` and
registers them with the relevant subsystem (channel,
provider, tool, agent harness).

### Why we deferred

Sprint 32 P0-1 already shipped 5 typed registries:
`ToolRegistry` / `AsrRegistry` / `TtsRegistry` /
`VadRegistry` / `AgentRegistry`. The contracts cover:

- Decorator-based registration
  (`@register_tool("name")`)
- Auto-discovery via eager imports
  (`app/tools/__init__.py` triggers every decorator)
- Manifest-style metadata in code (class attributes:
  `name`, `description`, `parameters`, `startup.sidecar`,
  etc.)
- Single source of truth for "what tools are available"

A parallel `PluginRegistry` with `openclaw.plugin.json`
would add:

- A second declarative surface (TOML/JSON file vs.
  Python class)
- Two ways to do the same thing (decorator vs. manifest)
- Double indirection (`app.plugins.<name>` wrapping
  `app.tools.<name>`)

That's net negative value. Revisit Tier 3 only if:

- We ever ship a marketplace / user-installed plugins flow
  (where JSON manifests are needed because the
  Python-source-of-truth is unavailable)
- We need to support plugins in a non-Python language
  (e.g. a CLI tool that ships a `.plugin.json` without
  Python binding)

Neither is in the current roadmap (Sprint 36-41), so
Tier 3 is deferred indefinitely.

## Test summary

| Test file | Count | Coverage |
|-----------|-------|----------|
| `tests/core/test_agent_context.py` | 12 | Tier 1 loader + cache + freshness + no-overwrite |
| `tests/core/test_skill_metadata.py` | 18 | Tier 2 loader + cache + frontmatter edge cases + `to_spec` integration |
| `tests/memory/test_user_memory.py` (updated) | 2 | Contract change for `build_system_prompt` |

Full backend test suite (excluding pre-existing slow
`test_voice_ws_tts.py`): **1188 passed, 11 failed**.

The 11 failures are all pre-existing `tests/core/` ×
`tests/tools/test_builder*` pollution (identical to
Sprint 32 P0/P1/P1.1/P1.2/P1.3 baselines). They reproduce
in any session where `tests/core/` runs before
`tests/tools/`, regardless of this sprint's changes.
Tracked in long-term memory §python-backend-patterns
under the "fixture pollution" heading.

## Open follow-ups

1. **Voice dashboard UI for workspace editing** — the
  cockpit could add a "Workspace" tab that shows the 7
  markdown files in a textarea + live-reload button.
  Deferred; the user can edit the files directly via
  `shell_exec cat ~/.gundam-halo/workspace/AGENTS.md` or
  any text editor (`code ~/.gundam-halo/workspace/`).
2. **Heartbeat implementation** — `HEARTBEAT.md` ships
  empty. When the launchd supervisor (Sprint 34) gets a
  heartbeat trigger, this file becomes the input.
  Deferred; the file format is stable but the
  scheduler-side wiring is not.
3. **`MEMORY.md` long-term distillation** — OpenClaw's
  `MEMORY.md` is the curated long-term memory that gets
  loaded only in main sessions (per `AGENTS.md` §Memory).
  Gundam Halo's equivalent is `app/memory/` (SQLite +
  FAISS), not a single markdown file. The contract
  is preserved (main-session-only) but the storage
  substrate differs. No action needed.

## Related

- `~/.openclaw/workspace/AGENTS.md` — the OpenClaw
  source-of-truth this sprint borrowed from
- `docs/FEATURE-SPEC-SPRINT32.md` — Sprint 32 P0-1 (the
  registry design Tier 3 would have duplicated)
- `app/agents/system_prompt.py` — the integration point
  for Tier 1's `format_for_prompt`
- `app/tools/_stubs.py::BaseTool.to_spec` — the integration
  point for Tier 2's `_get_skill_for_spec`
- `docs/CHANGELOG.md` — full Sprint 36 entry
# Feature Spec — Sprint 28: ToolsConfig + conditional tool registration

> **Status:** DRAFT — proposed Sprint 28 scope.
> **This is a SPEC-ONLY sprint.** No code is
> written. The implementation lands in Sprint 29
> (1 day wall clock) once the user signs off.
> **Predecessors:**
> - Sprint 27 (commit `4a7a83e`) shipped the
>   4 Mark-XL tools (`web_search`,
>   `youtube_summarize`, `flight_finder`,
>   `send_message`) — all 22 tools unconditionally
>   registered in `default_tools()`.
> - Sprint 27 spec (commit `aba7eb6`) §4.4
>   documented a `cfg.tools.<name>.enabled`
>   conditional registration pattern that the
>   implementation deferred to "a follow-up sprint".
> **Scope:** 1 day wall clock when implemented.
> The change is mostly mechanical:
>  1. Add a `ToolsConfig` dataclass + 4 nested
>     sub-configs to `app/core/config.py`
>    (~120 LoC).
>  2. Wire the 4 sub-configs into `load_config()`
>    (1 line).
>  3. Add a `tools: ToolsConfig` field to the
>    `Config` root dataclass (1 line).
>  4. Update `default_tools()` in
>    `app/tools/builder.py` to read
>    `cfg.tools.<name>.enabled` and conditionally
>    register each Mark-XL tool (~10 LoC).
>  5. Add 3 new test files (~200 LoC, ~15 tests).
>  6. Update `config.toml.example` (already has
>    `[tools.*]` sections from Sprint 27; no
>    change needed).
> **Out of scope (deferred to 29+):** runtime
> toggling of `enabled` via the dashboard, removal
> of the "reboot to take effect" caveat, additional
> `ToolConfig` fields (e.g. per-tool API keys).

---

## 0. Why this sprint exists

Sprint 27 (commit `4a7a83e`) shipped the
implementation of the Mark-XL tool import.
The implementation registered all 4 new tools
**unconditionally** in
`app/tools/builder.py::default_tools()`. The
Sprint 27 spec §4.4 documented a more
sophisticated pattern:

> All 4 tools are always registered in v0.1.5+;
> the user can disable them per-tool by editing
> `config.toml` and **rebooting the backend**.
> The full `cfg.tools.<name>.enabled` wiring is
> left for a follow-up sprint (Sprint 28+)
> because the `Config` dataclass in
> `app/core/config.py` already has 8
> sub-configs and adding a 9th (`ToolsConfig`)
> is a 1-day refactor that doesn't affect the
> 4 tools' behavior — they work the same
> either way.

Sprint 28 ships that 1-day refactor. The
change is **user-visible**: the user can
disable a tool by setting
`enabled = false` in `config.toml` and
**restarting the backend** (no code change
needed at runtime). The 4 tools become
**conditionally registered** — the agent
loop has no awareness of disabled tools,
which means the LLM never tries to call
them.

The change is **mostly mechanical** —
the dataclass + loader + 4 sub-configs
follow the exact pattern of the existing
8 sub-configs (`UserConfig`, `LLMConfig`,
`ServerConfig`, `MacControlConfig`,
`TelegramConfig`, `SecurityConfig`,
`VoiceConfig`, `MemoryConfig`). The test
suite is straightforward: ~15 tests
covering the dataclass defaults, the loader
fallbacks, and the conditional registration.

## 1. Goals

1. **Add a `ToolsConfig` dataclass** with 4
   nested sub-configs (`WebSearchConfig`,
   `YouTubeSummarizeConfig`,
   `FlightFinderConfig`, `SendMessageConfig`).
   Each sub-config has the fields that
   `config.toml.example` already documents
   (from Sprint 27).
2. **Wire the `ToolsConfig` into `Config`**
   so the singleton `get_config().tools`
   accessor works.
3. **Update `default_tools()`** in
   `app/tools/builder.py` to read
   `cfg.tools.<name>.enabled` and conditionally
   skip the 4 Mark-XL tools (and any future
   tools).
4. **Document the runtime-toggling caveat**:
   the user must restart the backend for
   `enabled = false` to take effect. A future
   sprint (Sprint 29+) can add a hot-reload
   path via the existing `restart_scheduled`
   pattern (Sprint 19b).
5. **No code is written in this sprint.**
   Sprint 28 is spec-only. The CHANGELOG
   entry is "Planned for v0.1.5+ (Sprint 29+)".

## 2. Out of scope (deferred)

- **Runtime toggling of `enabled`** — the
  user must restart the backend. A future
  sprint can wire `default_tools()` to be
  re-invoked when `tools.web_search.enabled`
  changes via the existing
  `put_voice_config` / `schedule_restart`
  pattern (Sprint 19b). Not in Sprint 28
  because the dashboard doesn't have a
  per-tool enable/disable UI yet.
- **Per-tool API keys** — `web_search` and
  `flight_finder` could accept an API key
  for a future "real" flight data extractor
  (Sprint 31+). Sprint 28 keeps the
  `ToolsConfig` extensible enough to add
  per-tool fields later, but doesn't add
  any.
- **Conditional registration for the
  pre-Sprint 27 tools** (`file_read`,
  `file_write`, `shell_exec`, etc.) — those
  tools don't have `enabled` fields in
  `config.toml` today. Adding them would
  be a 22-tool refactor (every existing
  tool needs a sub-config). Out of scope;
  the existing 21 tools are always-on.
- **Removal of the `config.toml.example`
  comments** that document the
  `enabled = false` default for
  `send_message` — the comment stays,
  the field becomes a real config field
  instead of a comment-only document.

## 3. User-facing behavior

This sprint is **mostly invisible to the
user** — the existing `config.toml.example`
already has `[tools.*]` sections with
`enabled = true` (or `false` for
`send_message`). Sprint 28 makes those
fields actually take effect.

**Before Sprint 28 (current state)**:
- The user sets `tools.send_message.enabled = false`
  in `~/.gundam-halo/config.toml`.
- The user restarts the backend.
- `default_tools()` still registers
  `SendMessageTool()` because the
  `enabled` field isn't wired to the
  config singleton.
- The agent has access to the tool; the
  LLM can call it; the tool returns
  "not yet implemented" because the
  user hasn't installed pyautogui.

**After Sprint 28 (target state)**:
- The user sets `tools.send_message.enabled = false`
  in `~/.gundam-halo/config.toml`.
- The user restarts the backend.
- `default_tools()` reads
  `cfg.tools.send_message.enabled` and
  skips `SendMessageTool()`.
- The agent has no awareness of the
  tool; the LLM's tool list does not
  include it. The LLM cannot call it.

The user-facing benefit: the user can
**cleanly disable a tool** without the
LLM attempting to call it and getting
back a "not implemented" error. The
user's tool list shrinks to 18 (web_search,
youtube_summarize, flight_finder all
enabled, send_message disabled) or
smaller (if multiple tools disabled).

**Restart-required caveat**: the
`enabled` field is **not** runtime-tunable.
The user must restart the backend for
the change to take effect. The
`config.toml.example` comment makes this
explicit:

```toml
# SendMessageTool (Track 27.4) — pyautogui-based
# message sender. **OPT-IN**: requires the
# `pyautogui + pyperclip` deps AND macOS Accessibility
# permission. The tool is a stub in v0.1.5+ — it
# returns a clear "not yet implemented" message.
#   uv add pyautogui pyperclip
#
# NOTE: changes to `enabled` take effect on backend
# restart. A future sprint will add hot-reload.
[tools.send_message]
enabled = false
```

## 4. Architecture

### 4.1 The 5 new dataclasses

`ToolsConfig` is a new dataclass in
`app/core/config.py` with 4 nested
sub-configs. Each sub-config is a
dataclass with the fields that
`config.toml.example` already documents.

```python
@dataclass
class WebSearchConfig:
    """Settings for the WebSearchTool (Sprint 27 Track 27.1).

    Per `docs/FEATURE-SPEC-SPRINT27.md` §4.2.
    """
    enabled: bool = True
    # Cap on results fetched from DDG (1-10). Default 5.
    max_results: int = 5
    # Cap on the formatted output length (chars)
    # to keep the TTS response under the 60s budget.
    summary_max_chars: int = 800
    # HTTP timeout for the DDG endpoint.
    request_timeout_s: float = 10.0


@dataclass
class YouTubeSummarizeConfig:
    """Settings for the YouTubeSummarizeTool (Sprint 27 Track 27.2)."""
    enabled: bool = True
    # Cap on transcript length before LLM
    # summarisation. Default 12000 (matches Mark-XL).
    max_transcript_chars: int = 12_000
    # Cap on the formatted output length (chars).
    summary_max_chars: int = 800


@dataclass
class FlightFinderConfig:
    """Settings for the FlightFinderTool (Sprint 27 Track 27.3).

    The tool is a URL builder in v0.1.5+ — no
    real flight-data extractor. A future
    sprint (Sprint 31+) can add a paid flight
    API key here.
    """
    enabled: bool = True
    # No config fields yet — the tool builds
    # a clean Google Flights URL from
    # origin/destination/date.


@dataclass
class SendMessageConfig:
    """Settings for the SendMessageTool (Sprint 27 Track 27.4).

    The tool is a stub in v0.1.5+ — the full
    pyautogui flow is a future sprint
    (Sprint 31+). The `enabled` flag defaults
    to `false` because pyautogui is fragile.
    """
    enabled: bool = False  # OPT-IN
    # Default messaging platform when none is specified.
    default_platform: str = "whatsapp"
    # OS family (auto-detected from sys.platform
    # by default). Uncomment to override.
    # os_system: str = "darwin"  # darwin | win32 | linux


@dataclass
class ToolsConfig:
    """Settings for the agent's tool registry.

    Per `docs/FEATURE-SPEC-SPRINT27.md` §4.4
    and `docs/FEATURE-SPEC-SPRINT28.md`.

    The 4 sub-configs control the 4 Mark-XL
    tools imported in Sprint 27. Each
    sub-config has an `enabled` flag that
    gates whether the tool is registered
    in the agent's tool list. A disabled
    tool is invisible to the LLM (the
    agent's tool spec list does not include
    it).

    Changes to `enabled` take effect on
    backend restart (not runtime-tunable
    in v0.1.5+; a future sprint can add
    hot-reload via the existing
    `schedule_restart` pattern).
    """
    web_search: WebSearchConfig = field(
        default_factory=WebSearchConfig
    )
    youtube_summarize: YouTubeSummarizeConfig = field(
        default_factory=YouTubeSummarizeConfig
    )
    flight_finder: FlightFinderConfig = field(
        default_factory=FlightFinderConfig
    )
    send_message: SendMessageConfig = field(
        default_factory=SendMessageConfig
    )
```

### 4.2 Wire `ToolsConfig` into `Config` and `load_config()`

Two changes to `app/core/config.py`:

```python
# Line 282 (after `memory: MemoryConfig` field):
tools: ToolsConfig = field(default_factory=ToolsConfig)

# In load_config() at line 525 (after
# `memory=_load_memory_config(toml_data)`):
tools=_load_tools_config(toml_data),
```

The new `_load_tools_config` function (sibling
of `_load_memory_config`):

```python
def _load_tools_config(toml_data: dict) -> ToolsConfig:
    """Load the [tools.*] sections from TOML.

    All fields are optional and fall back to the
    ToolsConfig defaults. See
    `docs/FEATURE-SPEC-SPRINT28.md` for design
    rationale.
    """
    d = toml_data.get("tools", {})
    return ToolsConfig(
        web_search=WebSearchConfig(
            enabled=d.get("web_search", {}).get(
                "enabled", WebSearchConfig().enabled
            ),
            max_results=d.get("web_search", {}).get(
                "max_results", WebSearchConfig().max_results
            ),
            # ... etc for each field
        ),
        youtube_summarize=YouTubeSummarizeConfig(...),
        flight_finder=FlightFinderConfig(...),
        send_message=SendMessageConfig(...),
    )
```

A shorter pattern (using a helper) avoids
the boilerplate:

```python
def _load_sub_config(section_dict, sub_config_class):
    """Load a sub-config from its TOML section.
    Returns a sub_config_class instance with
    fields populated from `section_dict` (any
    missing fields fall back to defaults)."""
    defaults = sub_config_class()
    kwargs = {}
    for field in dataclasses.fields(sub_config_class):
        kwargs[field.name] = section_dict.get(
            field.name, getattr(defaults, field.name)
        )
    return sub_config_class(**kwargs)


def _load_tools_config(toml_data: dict) -> ToolsConfig:
    d = toml_data.get("tools", {})
    return ToolsConfig(
        web_search=_load_sub_config(
            d.get("web_search", {}), WebSearchConfig
        ),
        youtube_summarize=_load_sub_config(
            d.get("youtube_summarize", {}),
            YouTubeSummarizeConfig
        ),
        flight_finder=_load_sub_config(
            d.get("flight_finder", {}), FlightFinderConfig
        ),
        send_message=_load_sub_config(
            d.get("send_message", {}), SendMessageConfig
        ),
    )
```

This is a 20-LoC helper that scales to any
future sub-config. The Sprint 28 impl uses
this pattern.

### 4.3 Conditional registration in `default_tools()`

The current `default_tools()` (Sprint 27
impl) registers all 22 tools unconditionally.
Sprint 28 modifies it to read the
`ToolsConfig` and conditionally register the
4 Mark-XL tools:

```python
# In app/tools/builder.py:

def default_tools() -> list[BaseTool]:
    """Return the default set of tools available to agents.

    Sprint 28: conditionally register the 4
    Mark-XL tools based on `cfg.tools.<name>.enabled`.
    A disabled tool is invisible to the LLM
    (the agent's tool spec list does not include
    it). Changes to `enabled` take effect on
    backend restart — see
    `docs/FEATURE-SPEC-SPRINT28.md` for the
    restart caveat.
    """
    from app.core.config import get_config

    cfg = get_config()
    tools: list[BaseTool] = [
        # ... existing 21 always-on tools ...
        FileReadTool(),
        FileWriteTool(),
        # ... etc ...
    ]

    # Sprint 28: conditional Mark-XL tool registration
    if cfg.tools.web_search.enabled:
        tools.append(WebSearchTool())
    if cfg.tools.youtube_summarize.enabled:
        tools.append(YouTubeSummarizeTool())
    if cfg.tools.flight_finder.enabled:
        tools.append(FlightFinderTool())
    if cfg.tools.send_message.enabled:
        tools.append(SendMessageTool())

    return tools
```

The `get_config()` call is **lazy** (imported
inside the function, not at module level) so
that `default_tools()` doesn't trigger a
TOML parse during the test suite's module
import. The test suite uses
`monkeypatch.setattr(cfg.tools.web_search, "enabled", False)`
to flip individual tools on/off.

### 4.4 Test cases

3 new test files:

**`tests/core/test_tools_config.py`** (NEW) —
6-8 tests for the dataclass + loader:
- `test_tools_config_defaults` — every
  sub-config has the expected default
  values.
- `test_web_search_config_defaults` —
  `max_results=5`, `summary_max_chars=800`,
  `request_timeout_s=10.0`.
- `test_send_message_default_disabled` —
  `SendMessageConfig().enabled == False` (the
  one opt-in default).
- `test_load_tools_config_empty_toml` —
  `toml_data = {}` returns all defaults.
- `test_load_tools_config_partial_override` —
  setting `[tools.web_search] max_results = 10`
  in TOML gives `cfg.tools.web_search.max_results == 10`
  while other fields stay default.
- `test_load_tools_config_send_message_override` —
  setting `[tools.send_message] enabled = true`
  flips the default to True.
- `test_load_tools_config_all_disabled` —
  setting all 4 `enabled = false` returns
  `ToolsConfig` with all disabled.
- `test_load_tools_config_missing_section` —
  `[tools]` section entirely missing gives
  defaults.

**`tests/tools/test_builder_conditional.py`**
(NEW) — 4-6 tests for the conditional
registration:
- `test_all_enabled_default_22_tools` — fresh
  config gives 22 tools.
- `test_disabled_send_message_yields_21_tools`
  — set `cfg.tools.send_message.enabled = False`,
  `default_tools()` returns 21 (no
  SendMessageTool).
- `test_disabled_all_yields_18_tools` — set
  all 4 Mark-XL tools disabled, returns 18
  (just the pre-Sprint 27 tools).
- `test_disabled_tool_not_in_specs` — when a
  tool is disabled, its `to_spec()` is not
  in the list of OpenAI specs returned by
  the agent.
- `test_enabled_flag_loaded_from_toml` —
  write a temp `config.toml` with
  `[tools.web_search] enabled = false`,
  reload config, assert the tool is
  disabled.
- `test_unknown_tool_section_ignored` —
  `[tools.bogus]` section in TOML is ignored
  (no error, no `BogusConfig` instantiation).

**`tests/tools/test_builder.py`** (UPDATED) —
1 existing test needs a small update:
- `test_default_tool_count_is_22` — keeps
  the 22-tool assertion (the default state
  is all-4-enabled, which matches the
  current code's "always register" behavior).
- New: `test_default_tool_count_with_send_message_disabled_yields_21`
  — set `cfg.tools.send_message.enabled = False`
  and verify the count drops to 21.

**Total**: ~200 LoC, ~15 tests across 3 files
(8 in `test_tools_config.py` + 6 in
`test_builder_conditional.py` + 1 new in
`test_builder.py`).

### 4.5 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **Dataclass field order matters for TOML parsing** | Low | Low | `dataclasses.fields(cls)` returns fields in declaration order, which matches Python's standard class attribute definition order. The `_load_sub_config` helper iterates fields in declaration order, so a new field added to the bottom of a sub-config dataclass is correctly read from TOML. |
| **`get_config()` import in `default_tools()` creates a circular import** | Low | Medium | The `get_config()` import is **lazy** (inside the function body, not at module level). `app.core.config` imports nothing from `app.tools.builder`, so the chain is acyclic. If a future refactor adds an import cycle, the `default_tools()` will raise `ImportError` at the first call, which the test suite catches. |
| **Disabled tool not removed from `Config.tools` field** | Low | Low | The `ToolsConfig` dataclass instantiates all 4 sub-configs by default. Setting `tools.web_search.enabled = False` flips the flag but doesn't remove the sub-config from the `ToolsConfig` parent. This is intentional: the user may want to inspect the disabled sub-config (e.g. to see what `max_results` would have been if enabled). |
| **Restart-required caveat is missed by users** | Medium | Low | The `config.toml.example` comment explicitly notes "changes to `enabled` take effect on backend restart". The CHANGELOG entry also notes this. A future sprint can add a dashboard banner that detects `config.toml` changes (mtime check) and prompts the user to restart. |
| **`default_tools()` called at import time** | Low | Medium | The current code in `app/api/sessions.py:124` calls `default_tools()` inside a request handler, not at import. This is correct — `default_tools()` reads `cfg.tools.<name>.enabled` at call time, so changes to the config singleton are picked up on the next request. If a future refactor moves the call to import time, the tool list would freeze at startup. |
| **The 4 sub-config dataclasses grow over time** | Low | Low | The `_load_sub_config` helper handles any number of fields automatically. Adding a new field to a sub-config (e.g. `WebSearchConfig.region: str = "wt-tr"` for DDG region) requires only 1 line in the dataclass + 1 line in `config.toml.example`. |
| **The user disables all 4 tools** | Low | Low | The 18 pre-Sprint 27 tools (file ops, Mac control, memory, weather, etc.) stay available. The agent still has 18 tools to work with. The 4 Mark-XL tools are opt-in; disabling them is a legitimate config (e.g. for an enterprise deployment that wants to lock down the agent's web access). |
| **The user disables a tool that's a dependency of another tool** | Low | Low | None of the 4 Mark-XL tools depend on each other or on any of the 18 pre-Sprint 27 tools. The dependency graph is: `ToolsConfig → 4 sub-configs → 4 tools`. Disabling one tool affects only that tool. |
| **The `_load_sub_config` helper mishandles nested types** | Low | Low | The current sub-configs have only `bool` / `int` / `float` / `str` fields. If a future sub-config has a `list` or `dict` field, the helper would need to be extended. For Sprint 28, the simple case is sufficient. |
| **The Sprint 27 `flight_finder` and `send_message` config fields are different** | Low | Low | `FlightFinderConfig` has only `enabled` (no other fields — the URL builder doesn't need them). `SendMessageConfig` has `enabled` + `default_platform` (the platform default for `run()` calls). The helper handles both cases uniformly. |

## 5. File-by-file change set (when Sprint 29 lands)

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/core/config.py` | Add 5 new dataclasses (`WebSearchConfig`, `YouTubeSummarizeConfig`, `FlightFinderConfig`, `SendMessageConfig`, `ToolsConfig`) + 1 new helper (`_load_sub_config`) + 1 new loader (`_load_tools_config`) + 1 field on `Config` + 1 line in `load_config()` | +120 / 0 |
| `backend/app/tools/builder.py` | `default_tools()` reads `get_config().tools.<name>.enabled` and conditionally registers the 4 Mark-XL tools | +15 / 0 |
| `backend/tests/core/test_tools_config.py` | NEW | +130 / 0 |
| `backend/tests/tools/test_builder_conditional.py` | NEW | +120 / 0 |
| `backend/tests/tools/test_builder.py` | Updated: 1 test name change + 1 new test for the disabled case | +20 / -5 |
| `config.toml.example` | No change (already has `[tools.*]` sections from Sprint 27; the comment is updated to note the restart caveat) | +5 / 0 |
| `docs/CHANGELOG.md` | v0.1.5+ ToolsConfig entry | +50 / 0 |

**Total**: ~460 LoC across 7 files.
~1 day wall clock when implemented
(spec-only sprint + 1-day impl sprint).

## 6. Sprint 28 vs Sprint 27 spec delta

The Sprint 27 spec (commit `aba7eb6`)
§4.4 documented the
`cfg.tools.<name>.enabled` pattern as a
deferral note. Sprint 28 ships the
implementation of that pattern.

**Sprint 27 spec §4.4 said**:
> The conditional registration pattern
> based on `cfg.tools.<name>.enabled` is
> documented in the spec §4.4 but is not
> yet wired in v0.1.5+ (a follow-up sprint
> can add it without changing the agent
> loop).

**Sprint 28 ships**:
1. The 5 new dataclasses (1 `ToolsConfig` +
   4 sub-configs).
2. The `_load_sub_config` helper (avoids
   boilerplate).
3. The 1-line change to `Config` (the
   `tools: ToolsConfig` field).
4. The 1-line change to `load_config()`
   (the `_load_tools_config(toml_data)`
   call).
5. The 4 conditional `if` blocks in
   `default_tools()`.
6. The 15 new tests.

The change is **forward-compatible**:
Sprint 27's `cfg.toml.example` already has
the `[tools.*]` sections. Sprint 28 makes
those sections actually take effect. The
`config.toml.example` doesn't need a
breaking change.

## 7. Out of scope (reaffirmed)

- **Runtime toggling of `enabled`** — the
  user must restart the backend. A future
  sprint can wire `default_tools()` to be
  re-invoked when `tools.web_search.enabled`
  changes via the existing
  `put_voice_config` / `schedule_restart`
  pattern (Sprint 19b).
- **Per-tool API keys** —
  `FlightFinderConfig` could accept an
  aviationstack / serpapi key in a future
  sprint (Sprint 31+). Sprint 28 keeps
  the `ToolsConfig` extensible.
- **Conditional registration for the
  pre-Sprint 27 tools** — `file_read`,
  `file_write`, etc. don't have
  `enabled` fields today. Adding them
  would be a 21-tool refactor. Out of
  scope.
- **Dashboard UI for tool enable/disable** —
  a future sprint can add a "Tools" tab
  in the cockpit settings.
- **Hot-reload of the tool list** — when
  the user edits `config.toml`, the
  backend currently requires a restart.
  A future sprint can add a
  `Watchdog` that detects mtime changes
  and re-invokes `default_tools()`.

## 8. Sign-off

- [ ] **`ToolsConfig` + 4 sub-configs
      agreed** — `WebSearchConfig` /
      `YouTubeSummarizeConfig` /
      `FlightFinderConfig` /
      `SendMessageConfig` (the 4 Mark-XL
      tools from Sprint 27).
- [ ] **`_load_sub_config` helper agreed** —
      generic sub-config loader that
      scales to any future sub-config.
- [ ] **Conditional registration agreed** —
      `default_tools()` reads
      `cfg.tools.<name>.enabled` and
      skips disabled tools.
- [ ] **Restart-required caveat agreed** —
      the user must restart the backend
      for `enabled` changes to take
      effect; documented in
      `config.toml.example` + CHANGELOG.
- [ ] **Out-of-scope items confirmed** —
      runtime toggling, per-tool API keys,
      pre-Sprint 27 tool enable/disable,
      dashboard UI, hot-reload.

---

## Appendix A — Why the 9th sub-config is OK

`app/core/config.py` already has 8
sub-configs. Adding a 9th (`ToolsConfig`)
brings the total to 9. Some readers may
worry that the config file is becoming
unwieldy. A few observations:

1. **TOML is structured** — the 9
   sub-configs map cleanly to TOML
   sections. A `config.toml` with 9
   sections is no harder to read than a
   `config.toml` with 8 sections.

2. **Each sub-config is small** — the
   largest (VoiceConfig) has 5
   nested sub-configs and ~30 fields.
   `ToolsConfig` has 4 nested
   sub-configs and 6 fields total. The
   average sub-config size is unchanged.

3. **Sub-configs are independent** —
   `ToolsConfig` doesn't depend on any
   other sub-config. The 4 sub-configs
   inside `ToolsConfig` don't depend on
   each other. The 9 sub-configs are
   parallel, not hierarchical.

4. **The dataclass pattern scales** —
   adding a 10th or 11th sub-config
   (e.g. `LoggingConfig`, `SecurityAuditConfig`)
   is the same 1-day refactor as adding
   this 9th. The pattern has been
   stable since Sprint 11.

5. **Most users only edit 1-2
   sub-configs** — the typical user
   edits `[llm]` + `[server]` at setup
   and never touches the rest. The
   9th sub-config is invisible to most
   users (the `config.toml.example` has
   the `[tools.*]` sections, but most
   users won't read them unless they
   want to disable a specific tool).

The 9-sub-config count is **fine**. The
refactor is **mechanical** and
**low-risk**. The user-facing benefit
(disable a tool without the LLM
attempting to call it) is **worth the
1-day refactor**.

## Appendix B — `default_tools()` and the lazy-import pattern

The `default_tools()` function in
`app/tools/builder.py` is called from
`app/api/sessions.py:124` (inside a
request handler). The function reads
`get_config().tools.<name>.enabled` to
decide which tools to register.

The naive implementation would import
`get_config` at the top of `builder.py`:

```python
# Top of builder.py:
from app.core.config import get_config  # BAD: forces TOML parse at import
```

This is **wrong** because:
1. `builder.py` is imported by many
   modules (e.g. `sessions.py`).
2. The TOML parse is expensive (~10ms
   on M-series, but cumulative over
   many imports).
3. The TOML parse may fail (file
   missing, malformed), and the failure
   would cascade to every module that
   imports `builder.py`.

The lazy-import pattern (inside the
function body) avoids all three issues:

```python
# In default_tools():
def default_tools() -> list[BaseTool]:
    from app.core.config import get_config
    cfg = get_config()
    # ...
```

This is the same pattern used by
`web_fetch.py` (lazy-imports the heavy
`httpx` import) and by Mark-XL's
`send_message.py` (lazy-imports
`pyautogui`). It's standard Python
practice for "import on first use".

The test suite uses
`monkeypatch.setattr(cfg.tools.web_search, "enabled", False)`
to flip the flag at runtime — the
`get_config()` singleton is already
populated, so the test can mutate the
config object directly without going
through the TOML parse path.

## Appendix C — `Config` field order and TOML

The `Config` dataclass's field order
matters for readability (the singleton
accesor is `cfg.<field_name>`), but
**not for TOML parsing**. The TOML
parse produces a flat dict; the loader
functions (`_load_user_config`,
`_load_llm_config`, etc.) pull their
respective sections. Reordering the
fields in `Config` doesn't change
TOML behavior.

The new `tools` field is added at the
**end** of `Config`'s field list (after
`memory`). This keeps the existing
sprint's field order intact (the diff
is purely additive — no field is moved
or renamed). The user can grep for
`^memory=` or `^tools=` in their
`config.toml` without worrying about
order.

## Appendix D — Sprint chain context

```
Sprint 28 — ToolsConfig + conditional registration (THIS SPRINT, spec-only)
Sprint 27 (4a7a83e) — Mark-XL tool import (impl)
Sprint 27 (aba7eb6) — Mark-XL tool import (spec)
Sprint 26 (9dc8761) — v0.1.5+ post-land menu
Sprint 25 (1461ce8) — v0.1.4 finalization (Track 3 impl template)
Sprint 24 (c24eb85) — v0.1.4 finalization (Track 3 acceptance gate)
Sprint 23 (4e85e99) — v0.1.4 land impl (Tracks 1+2+4)
Sprint 22 (e0b87f9) — v0.1.4 land plan
Sprint 21 (3353106) — prepare_common_voice_yue impl
Sprint 20 (ffc2624) — M9-E Layer 2 v0.1.4 rollout plan (spec-only)
Sprint 19d addendum (a8d8e17) — training monitor
Sprint 19d (0388699) — M9-E Layer 2 prep
... (earlier sprints)
```

Sprint 28 is the **first follow-up sprint
after Sprint 27** (the Mark-XL tool
import). It closes the gap that Sprint
27's "all-4-unconditional" implementation
left open. The next follow-up sprints
(Sprint 29+) can:

- Sprint 29: `send_message` real pyautogui
  impl (Sprint 31+ in the Sprint 27 spec
  but doable in Sprint 29 with
  computer-vision-based coordinates).
- Sprint 30: `flight_finder` real
  flight-data extractor (with a paid
  flight API).
- Sprint 31+: v0.1.5+ post-land menu
  items (Layer 2 v2 / launchd / held-out
  eval / mlx-whisper from Sprint 26).

## Appendix E — Test count evolution (cumulative)

| Sprint | New tests | Total backend tool tests |
|---|---|---|
| 27 (impl) | +78 | 172 (was 94) |
| **28 (spec-only)** | **0** | **172** |
| 29 (impl: ToolsConfig) | +15 | 187 |

Sprint 28 is spec-only, so 0 new tests.
Sprint 29 adds 15 tests across 3 files
(8 in `test_tools_config.py` + 6 in
`test_builder_conditional.py` + 1 new
in `test_builder.py`).

Total tool tests: 172 → 187 (+15).
Tool count stays at 22 (the count is
the same, the registration is
conditional).

## Appendix F — Why "restart required" is the right trade-off

A user might ask: "Why not make
`enabled` runtime-tunable? When I flip
the flag in `config.toml`, why does
the backend need a restart?"

The answer is **state management**:

1. **The LLM has a tool list.** The tool
   list is computed at agent-creation
   time (`sessions.py:124`) and cached.
   Changing the tool list mid-session
   would require invalidating all
   open agent sessions.

2. **The tool's `parameters` schema is
   part of the LLM's prompt context.**
   The schema is sent to the LLM on
   every turn. Changing the schema
   mid-session would confuse the LLM
   (it might try to call a tool that's
   no longer available).

3. **The tool's instance has state.**
   Some tools (e.g. `WhisperHFASR`)
   load models into memory at
   construction. Reloading a disabled
   tool's resources on the fly is
   non-trivial.

4. **The `restart_scheduled` pattern
   (Sprint 19b) is already in place**
   for ASR / corrector changes. The
   same pattern can be used for
   `tools.*.enabled` changes in a
   future sprint — but that's Sprint
   29+ scope, not Sprint 28.

The 1-day Sprint 28 refactor is the
**minimum viable** change. The
runtime-toggling feature is a
**separate sprint** that can build
on Sprint 28's foundation.

## Appendix G — Sprint 28 + Sprint 27 spec §4.4 reconciliation

Sprint 27 spec §4.4 (commit `aba7eb6`)
documented the `cfg.tools.<name>.enabled`
pattern as a deferral. The exact text
from the spec:

> The conditional registration pattern
> based on `cfg.tools.<name>.enabled` is
> documented in the spec §4.4 but is not
> yet wired in v0.1.5+ (a follow-up sprint
> can add it without changing the agent
> loop).

Sprint 28 ships that "follow-up sprint".
The spec structure is:

1. **Sprint 27 spec §4.4** (commit
   `aba7eb6`): documents the design
   pattern and the deferral.
2. **Sprint 27 impl** (commit `4a7a83e`):
   ships the 4 tools with
   `config.toml.example` already
   including the `[tools.*]` sections.
3. **Sprint 28 spec** (this commit):
   ships the design freeze for the
   `ToolsConfig` + conditional
   registration refactor.
4. **Sprint 29 impl**: ships the
   `ToolsConfig` + `default_tools()`
   conditional registration.

The 4-sprint chain (Sprint 27 spec →
Sprint 27 impl → Sprint 28 spec →
Sprint 29 impl) is the **canonical
"design freeze + implement" pattern**
that Gundam Halo has used since Sprint
16. Each sprint has a clear scope and
a clear handoff to the next.

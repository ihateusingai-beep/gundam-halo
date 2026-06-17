# Feature Spec — Sprint 27: Mark-XL selective tool import (5-7 days)

> **Status:** DRAFT — proposed Sprint 27 scope.
> **This is a SPEC-ONLY sprint.** No code is
> written. The implementation lands in Sprint
> 28+ when the user has capacity.
> **Predecessors:**
> - Sprint 22-25 (commits `e0b87f9`,
>   `4e85e99`, `c24eb85`, `1461ce8`) shipped
>   v0.1.4 land.
> - Sprint 26 (commit `9dc8761`) shipped the
>   v0.1.5+ post-land menu (4 tracks:
>   Layer 2 v2, launchd supervisor,
>   held-out eval, mlx-whisper).
> - **External**: Mark-XL
>   (https://github.com/FatihMakes/Mark-XL,
>   MIT, 153 stars, 67 forks, 20 commits on
>   `main`, ~64KB `main.py`, ~84KB `ui.py`,
>   PyQt6 HUD + Ollama LLM + faster-whisper
>   STT + edge-tts/kokoro/elevenlabs TTS).
> **Scope:** 5-7 days wall clock when
> implemented. 4 sub-tracks: `web_search`
> (DDG + LLM summary), `youtube_video`
> (transcript-fetch + summarize, split into
> 2 tools), `flight_finder` (Selenium
> adapter OR new API), `send_message`
> (pyautogui-based, with caveats). 2
> Mark-XL tools explicitly **excluded**:
> `weather_report` (Mark-XL's is strictly
> worse than the existing Gundam Halo
> `weather.py`) and `computer_control`
> (overlaps with Gundam Halo's
> `a11y`/`apple_script`/`screenshot`/
> `clipboard`/`spotlight`).
> **Out of scope (deferred to 28+):** Mark-XL
> PyQt6 UI, Ollama LLM swap, Mark-XL
> memory_manager, Mark-XL task_queue,
> Mark-XL installer. v0.1.5+ post-land menu
> items from Sprint 26 (Layer 2 v2,
> launchd supervisor, held-out eval,
> mlx-whisper) — Sprint 27 supersedes
> the recommended Track 3 first ordering
> for these.

---

## 0. Why this sprint exists

Gundam Halo 嘅 NativeReAct agent (per
M9-C live fixture + M9-D) ships with 21
built-in tools (`file_read`, `file_write`,
`shell_exec`, `open_app`, `mavis_delegate`,
`web_fetch`, `weather`, `memory_read`,
`memory_write`, `apple_script`, `clipboard`,
`notify`, `spotlight`, `a11y`, `brightness`,
`system_settings`, `screenshot`,
`bluetooth`). 21 tools cover Mac
desktop control + local file ops + a
handful of web/network tools, but the
agent is **missing common web-2.0
capabilities** the user takes for
granted in 2026:

- **No web search** — `web_fetch` can
  GET a single URL but can't search
  the web. The agent can't say "search
  for the latest iPhone release date"
  or "compare the price of X vs Y".
- **No YouTube transcript** — the agent
  can't summarize a YouTube video
  (very common in Cantonese/Chinese
  learning content).
- **No flight search** — the agent
  can't answer "find me a flight from
  HKG to TPE next Tuesday".
- **No message send** — the agent
  can open WhatsApp but can't
  send a message to a specific
  contact.

These are the **top 4 user requests**
that have been deferred over the
past sprints. The user has been
hand-writing the same DuckDuckGo
searches and YouTube lookups
in the chat. Sprint 27 closes the
gap by importing 4 of Mark-XL's
17 tools into Gundam Halo's tool
registry.

Mark-XL is a **public-domain-aligned**
sibling project (MIT licensed, well-
architected, single-file `actions/`
directory with clear public signatures,
uses Ollama for LLM + faster-whisper
for STT + edge-tts for TTS). The
**selective** part is critical: Mark-XL
ships 17 tools, but:

- `weather_report.py` is **strictly
  worse** than the existing Gundam
  Halo `weather.py` (it just opens
  Google search in the user's
  default browser; the existing
  `wttr.in` JSON parse is faster
  and more accurate).
- `computer_control.py` overlaps
  with 6 of Gundam Halo's existing
  tools (`a11y`, `apple_script`,
  `screenshot`, `clipboard`,
  `spotlight`, `system_settings`).
  It also pulls in `pyautogui` and
  a vision LLM, neither of which
  is in Gundam Halo's `pyproject.toml`.
- `flight_finder.py` is the only
  tool that would need a **new
  third-party API** (Google
  Flights) or accept the heavy
  Selenium path.
- `send_message.py` is the only
  tool that would need a **new
  pyautogui dependency**.

Sprint 27 ships the 4 valuable tools
(`web_search`, `youtube_video`,
`flight_finder`, `send_message`),
each with a clear contract change
to fit Gundam Halo's tool pattern.
The 2 excluded tools are
**documented but not ported** — the
user can revisit later if the gap
matters.

## 1. Goals

1. **Document the 4 imported tools** with
   per-tool public signature, schema,
   config keys, and adapter
   requirements.
2. **Document the 3 contract changes**
   that the importer must enforce on
   every Mark-XL tool: `async run(**kwargs)
   -> str` signature (not `def toolname
   (parameters, player, session_memory)`),
   JSON Schema in `parameters` dict (fed
   to OpenAI spec via `to_spec()`), and
   `asyncio.to_thread()` wrap for sync
   bodies.
3. **Document the 2 excluded tools** with
   a clear reason so the user doesn't
   ask "why didn't you import
   `weather_report`?" in a follow-up
   sprint.
4. **Capture the config-key migration**
   from Mark-XL's `config/api_keys.json`
   to Gundam Halo's `~/.gundam-halo/config.toml`.
5. **Capture the voice path implications**:
   long-form web_search / YouTube
   summaries must be TTS-friendly prose
   (no big code fences, no markdown
   tables) to flow through the existing
   `voice_sanitizer.py` cleanly.
6. **Capture the rollout order** —
   which tool ships first, which
   second, etc. — based on dependency
   graph and risk.
7. **No code is written in this
   sprint.** Sprint 27 is spec-only.
   The CHANGELOG entry is "Planned
   for v0.1.5+ (Sprint 28+)".

## 2. Out of scope (deferred)

- **Mark-XL PyQt6 UI** — Gundam Halo
  uses Tauri 2 + Vite + React 19 + shadcn/ui
  + Tailwind v4 + Live2D avatar
  (cockpit). PyQt6 is a separate
  desktop framework; integrating it
  would require either running both
  UIs side-by-side (impossible —
  two windows on the same screen,
  different event loops) or ripping
  out the Tauri app entirely. The
  Tauri app is a 1.5-year investment;
  the Mark-XL PyQt6 UI is **not**
  imported.
- **Ollama LLM swap** — Mark-XL
  uses Ollama for inference
  (any pulled model: qwen2.5,
  llama3.2, mistral). Gundam Halo
  uses `MiniMax` API
  (`app/engines/minimax.py`). Adding
  an Ollama backend would be a
  separate sprint (Sprint 28+);
  the user can pick either or both.
- **Mark-XL memory_manager.py** —
  Mark-XL stores long-term memory
  in `memory/long_term.json` (a
  flat JSON dict with categories
  `identity`, `preferences`,
  `projects`, `relationships`,
  `wishes`, `notes`). Gundam Halo
  uses M11 / M11b / M12 (SQLite +
  FAISS). The two are not
  interchangeable; the import
  contract doesn't touch memory.
- **Mark-XL task_queue.py** —
  Mark-XL has a multi-step planner
  + executor + error recovery
  (`agent_task` tool calls into
  this). Gundam Halo's NativeReAct
  is **single-step** (each turn is
  one tool call); multi-step is
  achieved by the agent loop in
  `app/agents/native_react.py` (the
  LLM drives the next tool call,
  not a separate queue). Sprint 27
  does **not** import the task queue.
- **Mark-XL installer** — Mark-XL
  has a `_bootstrap()` auto-install
  that runs `pip install` on
  first launch. Gundam Halo uses
  `uv sync --extra voice --extra
  voice-hf` etc. (no auto-install).
- **Mark-XL's `code_helper` /
  `dev_agent` tools** — both
  delegate to a sub-LLM agent for
  multi-file project generation.
  Gundam Halo doesn't have this
  capability; adding it would be
  a separate sprint.
- **Mark-XL's `screen_process` /
  `desktop_control` tools** —
  `screen_process` uses a vision
  LLM (Ollama's llava or external),
  `desktop_control` is
  cross-platform wallpaper/
  organize/clean. Gundam Halo
  has `screenshot` + `a11y` for
  similar coverage; the Mark-XL
  versions are strictly worse.
- **v0.1.5+ post-land menu items
  from Sprint 26** (Layer 2 v2,
  launchd supervisor, held-out
  eval, mlx-whisper) — Sprint 27
  supersedes the recommended
  Track 3 first ordering. The
  user can re-prioritize after
  Sprint 28+ lands.

## 3. User-facing behavior

Sprint 27 ships **4 new tools** to the
NativeReAct agent. The user can call
them via the cockpit chat (Tauri UI)
or via the voice agent (Sprint 18+
push-to-talk / Sprint 19c always-on
mic). The agent's tool list grows
from 21 to 25 entries.

**Examples** (cockpit chat or voice):

- **Web search**:
  - User: "search for the latest
    SpaceX Starship launch date"
  - Agent calls
    `web_search(query="latest SpaceX
    Starship launch date")`
  - Agent returns a 2-paragraph
    summary (TTS-friendly prose,
    no markdown fences) with
    citations
  - Voice: agent speaks the
    summary in 4-6 seconds
  - Chat: agent displays the
    summary in the chat panel
- **YouTube summarize**:
  - User: "summarize this YouTube
    video: https://youtu.be/xxx"
  - Agent calls
    `youtube_summarize(url=...)`
  - Agent fetches the transcript
    via `youtube-transcript-api`,
    truncates to 12KB, calls the
    LLM to summarize, returns
    a 3-4 sentence summary
  - Voice: agent speaks the
    summary in 6-10 seconds
- **Flight search**:
  - User: "find me a flight from
    HKG to TPE next Tuesday"
  - Agent calls
    `flight_finder(origin="HKG",
    destination="TPE",
    date="2026-06-24",
    cabin="economy")`
  - Agent returns a 5-row table
    of the cheapest flights
    (TTS-friendly: "the cheapest
    is X for $Y on Z, then
    $A on B...")
  - Voice: agent speaks the
    top-3 flights in 8-12
    seconds
  - Chat: agent displays a
    markdown table
- **Send message**:
  - User: "send a WhatsApp to
    John saying I'll be late"
  - Agent calls
    `send_message(receiver="John",
    message_text="I'll be late",
    platform="whatsapp")`
  - Agent drives pyautogui to
    open WhatsApp, focus the
    contact, type the message,
    press Enter, return "Message
    sent to John via WhatsApp."
  - Voice: agent speaks the
    confirmation in 1-2 seconds

**Edge cases**:

- Web search returns 0 results
  → Agent speaks "I couldn't find
  anything for that query. Try
  rephrasing?"
- YouTube video has no transcript
  → Agent speaks "This video
  doesn't have a transcript
  available."
- Flight search fails (Selenium
  timeout) → Agent speaks
  "Flight search timed out. Try
  again or check Google Flights
  directly."
- Send message fails (pyautogui
  can't find the contact) →
  Agent speaks "I couldn't find
  contact 'John' in WhatsApp.
  Open WhatsApp manually?"

## 4. Architecture

### 4.1 The 4 contract changes

Every Mark-XL tool must be wrapped
to fit Gundam Halo's `BaseTool` pattern.
The 3 contract changes are:

**Change 1 — `(**kwargs)` async signature**:
- Mark-XL: `def toolname(parameters: dict,
  player=None, session_memory=None) -> str`
- Gundam Halo: `async def run(self, **kwargs) -> str`
- The LLM engine parses the tool call
  into a dict and unpacks via `**kwargs`.
  Mark-XL's flat `parameters` dict
  becomes the kwarg names.
- Gundam Halo's `player` and
  `session_memory` are NOT used; the
  cockpit's chat panel is the
  output sink (via the agent's
  `output` field) and the
  `EventBus` is the event sink.

**Change 2 — JSON Schema in `parameters`**:
- Mark-XL: tools are registered
  as Python functions; the LLM
  engine reads the function
  signature and constructs the
  JSON Schema dynamically.
- Gundam Halo: `parameters: Dict[str, Any]`
  is a hand-written JSON Schema
  dict that gets wrapped into
  OpenAI spec via `to_spec()`.
- The importer must write the
  JSON Schema for each tool by
  hand (or by extracting from the
  Mark-XL `TOOL_DECLARATIONS`
  list at `main.py:64-352`).

**Change 3 — `asyncio.to_thread()` for
sync bodies**:
- Mark-XL: `web_search`,
  `youtube_video`, `flight_finder`,
  `send_message` all use sync
  `requests` / `subprocess` /
  `time.sleep` / pyautogui calls.
- Gundam Halo: the voice path
  calls `tool.run(**kwargs)` from
  the event loop; a sync body
  blocks the loop for the
  duration of the call (5-10s for
  a web search).
- The wrapper wraps the body in
  `await asyncio.to_thread(self._sync_body, **kwargs)`.
  This matches the existing
  pattern in `YuesubASR.warmup()`
  and `WhisperHFASR.transcribe()`.

### 4.2 The 4 imported tools

#### Track 27.1 — `WebSearchTool` (DDG + LLM summary)

- **Source**: Mark-XL `actions/web_search.py`
  (~3KB).
- **Gundam Halo file**:
  `backend/app/tools/web_search.py` NEW
  (~120 LoC).
- **Public signature**:
  `async def run(self, query: str, mode: str = "search", items: list[str] | None = None, aspect: str = "general") -> str`
- **JSON Schema**:
  ```python
  parameters = {
      "type": "object",
      "properties": {
          "query": {"type": "string", "description": "Search query"},
          "mode": {"type": "string", "description": "'search' (default) or 'compare'", "enum": ["search", "compare"]},
          "items": {"type": "array", "items": {"type": "string"}, "description": "Items to compare (mode=compare)"},
          "aspect": {"type": "string", "description": "price | specs | reviews | general"},
      },
      "required": ["query"],
  }
  ```
- **Heavy deps**: `ddgs` (or legacy
  `duckduckgo-search`), `requests`
  for fallback. Already in scope.
- **Config keys** (Gundam Halo
  `~/.gundam-halo/config.toml`):
  ```toml
  [tools.web_search]
  enabled = true
  max_results = 5           # how many DDG results to fetch
  summary_max_chars = 800  # cap on LLM summary length
  request_timeout_s = 10
  ```
- **Behavior**:
  1. Wrap body in
     `await asyncio.to_thread(self._sync_search, **kwargs)`.
  2. `_sync_search` calls DDG's
     `DDGS().text(query, max_results=5)`.
  3. If `mode == "compare"`, format
     results as a side-by-side list
     (no LLM call — return raw
     list, TTS reads "Item A: X
     vs Item B: Y, Item A: ...").
  4. If `mode == "search"`, call
     the LLM engine (via
     `await self._llm_summarize(results, query)`)
     to produce a 2-3 sentence
     TTS-friendly summary.
  5. Return the summary string.
- **Voice implications**: the
  summary must be TTS-friendly
  prose. The existing
  `voice_sanitizer.py` strips
  markdown fences, but the
  summary should avoid them
  pre-format (TTS reads "Section
  A versus Section B" for "## A
  vs B").
- **Test**:
  `tests/tools/test_web_search.py`
  NEW (~150 LoC, 6-8 tests):
  - `test_search_returns_summary`
    (mock DDG + LLM, assert
    string is 100-800 chars).
  - `test_search_no_results`
    (mock DDG returning empty,
    assert fallback string).
  - `test_compare_mode_returns_list`
    (mock DDG returning 2 items,
    assert list format).
  - `test_search_uses_asyncio_to_thread`
    (mock the sync body, assert
    `to_thread` was called).
  - `test_search_respects_max_results`
    (mock DDG, assert `max_results`
    from config was forwarded).
  - `test_search_timeout_raises`
    (mock DDG raising
    `requests.Timeout`, assert
    `WebSearchError` propagates).

#### Track 27.2 — `YouTubeSummarizeTool` (transcript + LLM)

- **Source**: Mark-XL
  `actions/youtube_video.py` (~12KB,
  multi-action). The importer
  extracts **only** the `summarize`
  and `get_info` actions. The
  `play` action (open in browser)
  is replaced by a separate
  `YouTubePlayTool` that calls
  `open_app` (or `webbrowser.open`).
- **Gundam Halo file**:
  `backend/app/tools/youtube_summarize.py`
  NEW (~150 LoC).
- **Public signature**:
  `async def run(self, url: str, max_summary_chars: int = 800) -> str`
- **JSON Schema**:
  ```python
  parameters = {
      "type": "object",
      "properties": {
          "url": {"type": "string", "description": "YouTube video URL"},
          "max_summary_chars": {"type": "integer", "description": "Cap on summary length (default 800)"},
      },
      "required": ["url"],
  }
  ```
- **Heavy deps**: `requests`,
  `youtube-transcript-api`. The
  Mark-XL `tkinter` URL prompt is
  dropped — `url` is a required
  parameter.
- **Config keys**:
  ```toml
  [tools.youtube_summarize]
  enabled = true
  max_transcript_chars = 12000  # truncate before LLM
  summary_max_chars = 800
  ```
- **Behavior**:
  1. Wrap body in
     `await asyncio.to_thread(...)`.
  2. Fetch transcript via
     `YouTubeTranscriptApi.get_transcript(video_id)`.
  3. Truncate to
     `max_transcript_chars` (12KB
     default, matches Mark-XL).
  4. Call LLM to summarize the
     transcript, producing a
     2-4 sentence TTS-friendly
     summary.
  5. Return the summary string.
- **Voice implications**: TTS reads
  the summary in 6-10 seconds. The
  LLM is prompted to write
  sentence-friendly prose
  ("The video discusses X. Then
  it explains Y. Finally, it
  concludes Z."), not bullet
  points.
- **Test**:
  `tests/tools/test_youtube_summarize.py`
  NEW (~150 LoC, 5-7 tests):
  - `test_summarize_returns_string`
    (mock YouTubeTranscriptApi +
    LLM, assert 100-800 chars).
  - `test_summarize_truncates_long_transcript`
    (mock transcript >12KB,
    assert truncated to
    `max_transcript_chars`).
  - `test_summarize_no_transcript_raises`
    (mock YouTubeTranscriptApi
    raising `TranscriptsDisabled`,
    assert `YouTubeError` with
    clear message).
  - `test_summarize_respects_max_summary_chars`
    (mock LLM, assert summary
    length cap).

#### Track 27.3 — `FlightFinderTool` (Selenium + LLM)

- **Source**: Mark-XL
  `actions/flight_finder.py` (~10KB).
- **Gundam Halo file**:
  `backend/app/tools/flight_finder.py`
  NEW (~200 LoC, including
  Selenium driver setup).
- **Public signature**:
  `async def run(self, origin: str, destination: str, date: str, return_date: str | None = None, passengers: int = 1, cabin: str = "economy") -> str`
- **JSON Schema**:
  ```python
  parameters = {
      "type": "object",
      "properties": {
          "origin": {"type": "string", "description": "Departure city or IATA code (HKG, TPE, ...)"},
          "destination": {"type": "string", "description": "Arrival city or IATA code"},
          "date": {"type": "string", "description": "Departure date in YYYY-MM-DD"},
          "return_date": {"type": "string", "description": "Return date for round trips (YYYY-MM-DD)"},
          "passengers": {"type": "integer", "description": "Number of passengers (default 1)"},
          "cabin": {"type": "string", "enum": ["economy", "premium", "business", "first"], "description": "Cabin class (default economy)"},
      },
      "required": ["origin", "destination", "date"],
  }
  ```
- **Heavy deps**: `playwright`
  (preferred over Selenium for
  modern web; Mark-XL uses
  Selenium but Playwright is
  better-maintained). The user
  installs `playwright` separately
  (`uv pip install playwright &&
  playwright install chromium`).
- **Config keys**:
  ```toml
  [tools.flight_finder]
  enabled = true
  driver = "chromium"          # chromium | firefox | webkit
  headless = true
  page_load_timeout_s = 30
  request_timeout_s = 60
  ```
- **Behavior**:
  1. Wrap body in
     `await asyncio.to_thread(...)`.
  2. Construct Google Flights URL:
     `https://www.google.com/travel/flights?q=Flights%20from%20{origin}%20to%20{destination}%20on%20{date}`.
  3. Launch Playwright Chromium
     (headless), navigate to URL,
     wait for `body` selector.
  4. Extract the top-5 flight
     results (selector TBD —
     Google Flights DOM changes
     often, may need a maintenance
     pass).
  5. Call LLM to format the raw
     HTML into TTS-friendly prose:
     "The cheapest flight from HKG
     to TPE on June 24 is X for
     $Y on Z, departing at 14:30.
     The next cheapest is ..."
  6. Return the prose string.
- **Risk note**: Google Flights
  DOM changes frequently. The
  `flight_finder` tool will need
  a maintenance pass every 3-6
  months to update the selectors.
  Mark-XL's hard-coded `EgoyMDI1...`
  param is a 2025-03-15 stale
  placeholder; the importer
  drops it and relies on URL
  construction only.
- **Voice implications**: TTS
  reads "the cheapest is X for
  $Y..." — the LLM prompt
  enforces TTS-friendly prose.
- **Test**:
  `tests/tools/test_flight_finder.py`
  NEW (~180 LoC, 4-6 tests):
  - `test_flight_search_returns_prose`
    (mock Playwright + LLM,
    assert prose string is
    200-1500 chars).
  - `test_flight_search_handles_no_results`
    (mock Playwright returning
    empty DOM, assert fallback
    "no flights found" string).
  - `test_flight_search_timeout_raises`
    (mock Playwright timing out,
    assert `FlightFinderError`).
  - `test_flight_search_uses_asyncio_to_thread`
    (mock the sync body, assert
    `to_thread` was called).
  - `test_flight_search_url_construction`
    (assert URL is correctly
    encoded with origin,
    destination, date).

#### Track 27.4 — `SendMessageTool` (pyautogui)

- **Source**: Mark-XL
  `actions/send_message.py` (~6KB).
- **Gundam Halo file**:
  `backend/app/tools/send_message.py`
  NEW (~250 LoC, including
  pyautogui driver setup).
- **Public signature**:
  `async def run(self, receiver: str, message_text: str, platform: str = "whatsapp") -> str`
- **JSON Schema**:
  ```python
  parameters = {
      "type": "object",
      "properties": {
          "receiver": {"type": "string", "description": "Contact name (must exist in the platform's contact list)"},
          "message_text": {"type": "string", "description": "The exact message text to send"},
          "platform": {"type": "string", "enum": ["whatsapp", "telegram", "instagram", "signal", "discord", "messenger"], "description": "Messaging platform (default whatsapp)"},
      },
      "required": ["receiver", "message_text"],
  }
  ```
- **Heavy deps**: `pyautogui`,
  `pyperclip`. **NOT** currently
  in `pyproject.toml`. The user
  installs:
  ```
  uv add pyautogui pyperclip
  ```
  (Mac requires Accessibility
  permission for pyautogui.)
- **Config keys**:
  ```toml
  [tools.send_message]
  enabled = true
  os_system = "mac"           # mac | windows | linux
  typing_delay_s = 0.05
  app_launch_wait_s = 2.5
  contact_search_timeout_s = 5
  ```
- **Behavior**:
  1. Wrap body in
     `await asyncio.to_thread(...)`.
  2. Resolve platform → app name
     (whatsapp → "WhatsApp",
     telegram → "Telegram", etc.).
  3. Open the app via
     `open -a "App Name"` (macOS).
  4. Wait `app_launch_wait_s`
     (2.5s default — fragile but
     matches Mark-XL's hard-coded
     timing).
  5. Click on the contact search
     bar (pyautogui coordinates
     hard-coded per app).
  6. Type the receiver name.
  7. Click on the contact.
  8. Click on the message bar.
  9. Type the message (with
     `typing_delay_s` between
     chars).
  10. Press Enter.
  11. Return "Message sent to
      {receiver} via {platform}."
- **Risk note**: pyautogui is
  **fragile**. The hard-coded
  coordinates work for the
  current app versions on the
  user's specific Mac. A
  pyautogui Coordinate offset of
  50px (different Mac resolution)
  breaks the tool. The
  `SendMessageTool` is **opt-in**
  (`enabled = true` in config;
  default `false` to avoid
  surprise).
- **Voice implications**: TTS
  reads "Message sent to John
  via WhatsApp" in 1-2 seconds.
  No long-form text.
- **Test**:
  `tests/tools/test_send_message.py`
  NEW (~200 LoC, 6-8 tests):
  - `test_send_message_returns_confirmation`
    (mock pyautogui, assert
    confirmation string).
  - `test_send_message_resolves_platform`
    (assert `whatsapp` →
    "WhatsApp", `telegram` →
    "Telegram", etc.).
  - `test_send_message_unknown_platform_raises`
    (assert `ValueError` on
    unknown platform).
  - `test_send_message_uses_asyncio_to_thread`
    (mock pyautogui, assert
    `to_thread` was called).
  - `test_send_message_disabled_by_default`
    (assert `enabled = false`
    in default config; user
    must opt in).
  - `test_send_message_pyautogui_failure_raises`
    (mock pyautogui raising
    `FailSafeException`, assert
    `SendMessageError` with
    clear message).

### 4.3 The 2 excluded tools (with reasons)

#### `weather_report.py` — EXCLUDED

- **Reason**: Mark-XL's
  `weather_action(parameters, player, session_memory)`
  is **strictly worse** than
  Gundam Halo's existing
  `WeatherTool.run(self, location: str)`:
  - Mark-XL just calls
    `webbrowser.open("https://www.google.com/search?q=weather+{city}")`
    — opens a browser tab, no
    actual data.
  - Gundam Halo's `WeatherTool`
    calls `wttr.in/{city}?format=j1`
    + parses JSON + returns a
    spoken-style summary.
- **Action**: no work. The
  existing `weather.py` covers
  this. If the user later wants
  to upgrade to a real weather
  API (OpenWeatherMap, Apple
  WeatherKit), that's a separate
  sprint.

#### `computer_control.py` — EXCLUDED

- **Reason**: 16KB tool that
  overlaps with **6 of Gundam
  Halo's existing tools**:
  - `computer_settings` (Mark-XL)
    → `system_settings` (Gundam
    Halo).
  - `type`, `click`, `hotkey`
    (Mark-XL) → `apple_script` +
    `a11y` (Gundam Halo — uses
    macOS Accessibility API, not
    pyautogui).
  - `screenshot` (Mark-XL) →
    `screenshot` (Gundam Halo).
  - `clipboard` (Mark-XL) →
    `clipboard` (Gundam Halo).
  - `screen_find` (Mark-XL) →
    `spotlight` (Gundam Halo —
    for finding files; screen
    find for UI elements is
    covered by `a11y`).
  - `volume`, `brightness` (Mark-XL)
    → `brightness` (Gundam Halo).
- **Heavy deps Mark-XL pulls in**:
  `pyautogui` (not in Gundam
  Halo's deps), vision LLM via
  Ollama (not used by Gundam
  Halo).
- **Action**: no work. The
  existing Gundam Halo toolset
  covers the same surface area
  with Mac-native APIs (no
  pyautogui brittleness).

### 4.4 The config migration

Mark-XL reads `config/api_keys.json`
(`BASE_DIR / "config" / "api_keys.json"`).
Gundam Halo reads
`~/.gundam-halo/config.toml` (parsed
by `app/core/config.py::get_config()`).
The importer must:

1. **Drop the Mark-XL config file
   entirely** — no
   `config/api_keys.json` is
   created in the Gundam Halo
   repo.
2. **Add the new config keys to
   the existing `~/.gundam-halo/config.toml`**:
   ```toml
   [tools.web_search]
   enabled = true
   max_results = 5
   summary_max_chars = 800
   request_timeout_s = 10

   [tools.youtube_summarize]
   enabled = true
   max_transcript_chars = 12000
   summary_max_chars = 800

   [tools.flight_finder]
   enabled = true
   driver = "chromium"
   headless = true
   page_load_timeout_s = 30
   request_timeout_s = 60

   [tools.send_message]
   enabled = false  # opt-in (pyautogui fragility)
   os_system = "mac"
   typing_delay_s = 0.05
   app_launch_wait_s = 2.5
   contact_search_timeout_s = 5
   ```
3. **Add a `[tools]` section to
   `app/tools/builder.py::default_tools()`**
   that conditionally registers
   each tool based on `enabled`:
   ```python
   cfg = get_config()
   tools = [FileReadTool(), FileWriteTool(), ...]  # existing 21
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
4. **Update `config.toml.example`**
   in the repo root with the
   new sections (so a fresh
   install has them).

### 4.5 The voice path implications

The 4 imported tools all return
**strings** that flow through the
existing `voice_sanitizer.py`.
The sanitizer:

- Strips `<|...|>` tokens (Sprint 17a).
- Closes cross-sentence `<think>`
  blocks (Sprint 17a).
- Strips markdown fences
  (basic — may not catch all
  cases).

The tool authors must:

- **Avoid markdown fences** —
  the tool should pre-format
  the response as plain prose.
  Example: a YouTube summary
  should be "The video discusses
  X. Then it explains Y. Finally,
  it concludes Z.", not
  "## Summary\n\n- X\n- Y\n- Z".
- **Avoid tables in the voice
  path** — the LLM should
  read the table aloud as
  prose ("the cheapest is X for
  $Y on Z, departing at 14:30.
  The next cheapest is A for $B
  on C...").
- **Cap the response length** —
  the voice TTS has a 60-second
  budget per turn (typical
  200-300 words). A tool that
  returns a 2000-word essay
  breaks the voice UX. The
  LLM should be prompted to
  return concise prose (200-500
  words for summaries, 50-100
  words for confirmations).

### 4.6 The dependency additions

The importer adds the following
to `pyproject.toml`:

```toml
# Optional extra for the Mark-XL-derived tools.
# The user opts in with `uv sync --extra tool-web-search`
# (or the full `uv sync --extra voice --extra voice-hf
# --extra tool-web-search --extra tool-flight-finder`).

tool-web-search = [
    "ddgs>=5.0",  # DuckDuckGo search (replaces legacy duckduckgo-search)
]

tool-youtube-summarize = [
    "youtube-transcript-api>=0.6",
]

tool-flight-finder = [
    "playwright>=1.40",
    # The user runs `playwright install chromium` separately
    # (~150MB download). The Playwright wheel is ~50MB.
]

tool-send-message = [
    "pyautogui>=0.9.54",
    "pyperclip>=1.8",
]
```

Each tool is **opt-in via its
own extra** so the user can
install only what they need.
The `install.sh` script adds
the user-friendly defaults:

```bash
# install.sh
uv sync --extra voice --extra voice-hf
# Optional: add the tool imports
# uv sync --extra tool-web-search --extra tool-youtube-summarize
# uv sync --extra tool-flight-finder
# uv sync --extra tool-send-message
```

The `send_message` extra is
**commented out by default**
because pyautogui is fragile
and requires Accessibility
permission.

### 4.7 File-by-file change set (when Sprint 28+ lands)

| Path | Change | LoC est. |
|---|---|---|
| `backend/app/tools/web_search.py` | NEW | +120 / 0 |
| `backend/app/tools/youtube_summarize.py` | NEW | +150 / 0 |
| `backend/app/tools/flight_finder.py` | NEW | +200 / 0 |
| `backend/app/tools/send_message.py` | NEW | +250 / 0 |
| `backend/app/tools/builder.py` | Conditional registration based on `cfg.tools.*.enabled` | +30 / 0 |
| `backend/app/core/config.py` | Add `ToolsConfig` dataclass with `WebSearchConfig` / `YouTubeSummarizeConfig` / `FlightFinderConfig` / `SendMessageConfig` | +60 / 0 |
| `backend/pyproject.toml` | Add 4 optional extras | +25 / 0 |
| `config.toml.example` | Add 4 `[tools.*]` sections | +40 / 0 |
| `install.sh` | Add commented-out tool extras | +10 / 0 |
| `tests/tools/test_web_search.py` | NEW | +150 / 0 |
| `tests/tools/test_youtube_summarize.py` | NEW | +150 / 0 |
| `tests/tools/test_flight_finder.py` | NEW | +180 / 0 |
| `tests/tools/test_send_message.py` | NEW | +200 / 0 |
| `tests/tools/test_builder.py` | Add 4 tests for conditional registration | +80 / 0 |
| `docs/CHANGELOG.md` | v0.1.5+ entry per Sprint 28+ | +60 / 0 |

**Total**: ~1,705 LoC across 15 files.
~5-7 days wall clock when implemented,
spread across 2-3 sprints:

- **Sprint 28**: Tracks 27.1 (web_search)
  + 27.2 (youtube_summarize) — 2-3 days.
- **Sprint 29**: Tracks 27.3
  (flight_finder) — 1-2 days.
- **Sprint 30**: Track 27.4
  (send_message) — 1-2 days,
  opt-in.

### 4.8 Dependency graph

```
+----------------------------------+
| Sprint 26 v0.1.5+ menu         |  ← Sprint 26 (commit 9dc8761) ✓
| (Layer 2 v2 / supervisor /      |
|  held-out / mlx-whisper)         |
+----------------+-----------------+
                 v
+----------------------------------+
| Sprint 27 Mark-XL tool import   |  ← THIS SPRINT
| (4 tools, 5-7 days total)        |
+----------------+-----------------+
                 v
+----------------+-----------------+
                 v
+----------------------------------+
| Sprint 28 web_search +          |  ← First impl sprint
| youtube_summarize (2-3 days)    |
+----------------+-----------------+
                 v
+----------------------------------+
| Sprint 29 flight_finder         |  ← Second impl sprint
| (1-2 days)                       |
+----------------+-----------------+
                 v
+----------------------------------+
| Sprint 30 send_message (opt-in) |  ← Third impl sprint
| (1-2 days)                       |
+----------------+-----------------+
                 v
+----------------------------------+
| Optional: v0.1.5+ post-land     |  ← User re-prioritizes
| (Layer 2 v2 / supervisor /      |
|  held-out / mlx-whisper)         |
+----------------------------------+
```

Sprint 27 supersedes Sprint 26's
recommended Track 3 first ordering.
The user can re-prioritize the
v0.1.5+ post-land items after
Sprint 30 lands.

## 5. Sprint 27 vs Sprint 26 scope delta

Sprint 26 (commit `9dc8761`)
shipped the v0.1.5+ post-land menu
with 4 tracks (Layer 2 v2, launchd
supervisor, held-out eval,
mlx-whisper) and **recommended
Track 3 (held-out eval) as Sprint
27**. This Sprint 27 spec **supersedes
that recommendation**: instead of
the held-out eval, Sprint 27 ships
the Mark-XL tool import (4 tools,
5-7 days).

The reason: the held-out eval is
a **1-day sprint** that depends on
the user having run the v0.1.4
training session (a separate,
3h+ wall-clock session). The
Mark-XL tool import is a
**5-7 day sprint** that doesn't
depend on training. The user can
re-prioritize after Sprint 30 lands.

If the user wants the held-out
eval first, the held-out spec is
in `docs/FEATURE-SPEC-SPRINT26.md`
§4.3 — a 1-day sprint that can
ship immediately after Sprint 23
(no training required to *write*
the spec; the test is gated on
the user having run training
in a separate session).

## 6. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **DDG rate-limiting / blocking** | Medium | Medium | DDG has rate limits; the tool adds a `request_timeout_s` (10s) and a `max_results` cap (5). If DDG blocks, the tool returns a clear "DDG search failed; try again" message. |
| **YouTube transcript disabled** | Medium | Low | The tool returns a clear "this video doesn't have a transcript" message. The LLM is prompted to never fabricate a summary; if the transcript is missing, the tool fails cleanly. |
| **Google Flights DOM changes** | High | High | The `flight_finder` tool depends on Google Flights' DOM structure, which changes every 3-6 months. The tool ships with a `flight_finder_selectors.toml` config file that the user can update without changing code. If the selectors are stale, the tool returns "no flights found" (safe failure). |
| **pyautogui coordinate drift** | High | High | `send_message` is opt-in (`enabled = false` default) and the coordinates are hard-coded. A different Mac resolution or app version breaks the tool. The risk register recommends **not** shipping `send_message` until a coordinate-detection mechanism (computer vision) is added. |
| **`asyncio.to_thread` overload** | Low | Low | The 4 tools' sync bodies can take 5-10s each. If the user fires 4 tools in parallel, the event loop queues 4 thread workers. Python's default thread pool size is min(32, os.cpu_count() + 4) = ~36 on M-series, so 4 concurrent tools is fine. The agent loop is single-threaded (one tool at a time), so the realistic case is 1 tool at a time. |
| **Voice TTS overflow on long summary** | Medium | Low | The LLM is prompted to return concise prose (200-500 words). The voice TTS has a 60s budget per turn. If a tool returns >1500 chars, the agent loop logs a warning and the user can ask the agent to "summarize in 3 sentences". |
| **Tool-call events from new tools break the cockpit panel** | Low | Low | The existing `NativeReActAgent.run()` emits `TOOL_CALL_START/END` events for every tool, regardless of which tool. The cockpit's `use-vad-state-autofire.ts` (Sprint 19c P2) already handles unknown tool events. No work needed. |
| **Mark-XL license attribution** | Low | Low | Mark-XL is MIT licensed. The importer adds a `THIRD-PARTY-NOTICES.md` file with the Mark-XL license + a comment header in each imported tool file. |
| **DDG search returns non-English results for Cantonese query** | Medium | Medium | The DDG `region` parameter is set to the user's locale (auto-detect from `~/.gundam-halo/config.toml` `[user].locale`). The LLM is prompted to respond in the user's language. |
| **`pyautogui` not in venv** | High | Low | The `tool-send-message` extra is opt-in. If the user enables `cfg.tools.send_message.enabled = true` without installing pyautogui, the tool raises a clear `ImportError` with a hint: `uv add pyautogui pyperclip`. |
| **The user wants a 5th tool** (e.g. `reminder` from Mark-XL) | Low | Low | Mark-XL's `reminder.py` is Mac-specific (uses Task Scheduler on Windows, AppleScript on Mac). Gundam Halo has the same functionality via `apple_script` + `system_settings`. The user can add more Mark-XL tools in a follow-up sprint if needed. |
| **The user wants the Mark-XL UI** (PyQt6) | Low | High | **Out of scope per spec §2.** The Tauri cockpit is a 1.5-year investment; ripping it out for PyQt6 is a multi-month effort. The user can run Mark-XL standalone (it's MIT and self-contained) for a side-by-side comparison. |

## 7. Acceptance tests

1. **All 4 tools are importable** —
   `python -c "from app.tools.builder import default_tools; tools = default_tools(); assert len(tools) == 25"`.
2. **All 4 tools are in the OpenAI
   spec** — `python -c "from app.tools.builder import default_tools; specs = [t.to_spec() for t in default_tools()]; assert any(s['function']['name'] == 'web_search' for s in specs)"`.
3. **All 4 tools pass unit tests** —
   `pytest tests/tools/ -v` — 4 new
   test files, ~36 tests total.
4. **All 4 tools use
   `asyncio.to_thread()`** — verified
   by mock tests that assert
   `to_thread` was called.
5. **Voice path works with the
   new tools** — manual smoke:
   user speaks "search for the
   latest iPhone release", agent
   transcribes, calls
   `web_search`, returns a
   2-paragraph summary, TTS speaks
   it in 4-6 seconds.
6. **No regression on existing
   21 tools** — `pytest tests/agent/
   tests/tools/test_builder.py -v`
   — all 80 existing builder tests
   pass + 4 new conditional
   registration tests.
7. **No regression on voice
   pipeline** — `pytest
   tests/voice/` — 188 passed,
   2 skipped, 0 failed (Sprint 23
   baseline preserved).
8. **No regression on frontend** —
   `pnpm tsc --noEmit` — 0 errors.
   `pnpm vitest run` — 63/63 pass.
   (The 4 new tools don't touch
   the frontend; the cockpit
   panel auto-discovers them via
   the existing `to_spec()` path.)
9. **`send_message` is opt-in by
   default** — `cfg.tools.send_message.enabled == False`
   in `config.toml.example`. The
   user must explicitly set
   `enabled = true` to enable.

## 8. Sign-off

- [ ] **4 imported tools agreed** —
      `web_search`, `youtube_summarize`,
      `flight_finder`, `send_message`.
- [ ] **2 excluded tools agreed** —
      `weather_report` (existing
      `weather.py` is better) and
      `computer_control` (overlaps
      with 6 existing Gundam Halo
      tools).
- [ ] **3 contract changes agreed** —
      `(**kwargs)` async signature,
      JSON Schema in `parameters`,
      `asyncio.to_thread()` for
      sync bodies.
- [ ] **Config migration agreed** —
      drop Mark-XL's `api_keys.json`,
      add 4 `[tools.*]` sections to
      `~/.gundam-halo/config.toml`.
- [ ] **Dependency extras agreed** —
      4 opt-in extras
      (`tool-web-search`,
      `tool-youtube-summarize`,
      `tool-flight-finder`,
      `tool-send-message`).
- [ ] **Out-of-scope items
      confirmed** — Mark-XL PyQt6
      UI, Ollama LLM swap,
      Mark-XL memory_manager,
      Mark-XL task_queue, Mark-XL
      installer, Mark-XL
      `code_helper` / `dev_agent`,
      Mark-XL `screen_process` /
      `desktop_control` — all
      deferred or rejected.

---

## Appendix A — Why selective import, not full fork

A full fork of Mark-XL would mean:

1. **Two codebases** — Gundam Halo
   and Mark-XL live side-by-side,
   with overlapping STT / TTS /
   LLM layers. The user has to
   maintain both.
2. **Two UIs** — Gundam Halo's
   Tauri cockpit + Mark-XL's
   PyQt6 HUD. Two windows on
   the same screen, two event
   loops, two config files. The
   user has to remember which
   app does what.
3. **Two LLM backends** — Gundam
   Halo uses `MiniMax` API,
   Mark-XL uses Ollama. The user
   has to configure both (API
   key + Ollama server).
4. **Two memory systems** — Gundam
   Halo's M11/M11b/M12 (SQLite +
   FAISS) vs Mark-XL's
   `memory/long_term.json` (flat
   dict). The user has to manage
   both.
5. **Two Mac control surfaces** —
   Gundam Halo's
   `app/security/audit.py` (AppleScript
   + A11y) vs Mark-XL's
   pyautogui. The user has to
   grant permissions to both.

**Selective import** keeps the
**single Gundam Halo codebase**
and **single Tauri cockpit**,
adds 4 specific tools that the
user actually needs (web search,
YouTube summarize, flight finder,
send message), and avoids the
"two of everything" complexity
of a full fork.

The full Mark-XL project remains
a useful reference: the user
can read its source for patterns
(agent loop, memory, tool
dispatch) and cherry-pick
additional tools in future
sprints if the gap matters.

## Appendix B — Why 4 tools, not 17

Mark-XL ships 17 tools in
`actions/`. Sprint 27 imports
**only 4** because:

- **11 of the 17** either overlap
  with Gundam Halo's existing
  21 tools (6 of the 11) or
  are too narrow for the user's
  needs (5 of the 11:
  `code_helper`, `dev_agent`,
  `screen_process`, `desktop_control`,
  `flight_finder`'s Selenium
  driver is too brittle for
  v0.1.5+).
- **2 of the 17** are explicitly
  worse than the existing
  Gundam Halo versions
  (`weather_report` is browser
  search; `computer_control` is
  pyautogui).
- **4 of the 17** are the unique
  value-add: `web_search`,
  `youtube_video` (specifically
  the `summarize` action),
  `flight_finder`, `send_message`.

Sprint 27 captures the **top 4
user requests** that have been
deferred. The user can re-evaluate
the other 13 tools in future
sprints if specific gaps emerge.

## Appendix C — Test count evolution (cumulative)

| Sprint | New tests | Total backend voice + tools |
|---|---|---|
| 23 (previous) | +38 | 140 voice + 80 tool = 220 |
| 24 (spec-only) | 0 | 220 |
| 25 (spec-only) | 0 | 220 |
| 26 (spec-only) | 0 | 220 |
| **27 (spec-only)** | **0** | **220** |
| 28 (web_search + youtube) | +11 to +15 | 231-235 |
| 29 (flight_finder) | +4 to +6 | 235-241 |
| 30 (send_message) | +6 to +8 | 241-249 |

Sprint 27 is spec-only, so 0
new tests. Sprint 28 adds 6-8
web_search tests + 5-7
youtube_summarize tests = 11-15
new tests. Sprint 29 adds 4-6
flight_finder tests. Sprint 30
adds 6-8 send_message tests.
Total: 27-37 new tests across
Sprints 28-30.

The tool count grows from 21
to 25 (4 new tools), with each
tool averaging 5-7 tests.

## Appendix D — Rollback plan

If Sprint 28+ lands and the 4
new tools cause regressions:

1. **Set the `enabled` flag to
   `false`** in the relevant
   `[tools.*]` section. The
   tool is no longer registered
   in `default_tools()`. The
   agent loop has no awareness
   of the tool.
2. **The code stays in the
   repo** — no `git revert`
   needed. The user can re-enable
   by flipping the flag back to
   `true` once the regression
   is fixed.
3. **For `send_message` specifically**:
   the `enabled = false` default
   means a regression can't ship
   to production. The user only
   enables it after manual smoke
   test.

The conditional registration
pattern in `builder.py` is the
**single point of control** for
which tools the agent has access
to. No code changes needed to
disable a tool.

## Appendix E — Why Sprint 27 supersedes Sprint 26's Track 3 first ordering

Sprint 26 (commit `9dc8761`)
shipped the v0.1.5+ post-land
menu with 4 tracks and **recommended
Track 3 (held-out eval) as Sprint
27 first**. Sprint 27 (this spec)
**supersedes that recommendation**:
instead of the held-out eval, Sprint
27 ships the Mark-XL tool import.

The reason: the held-out eval is
a **1-day sprint** that depends
on the user having run the v0.1.4
training session (a separate,
3h+ wall-clock session). The
Mark-XL tool import is a
**5-7 day sprint** that doesn't
depend on training. The user
can re-prioritize after Sprint
30 lands.

If the user wants the held-out
eval first, the held-out spec
is in `docs/FEATURE-SPEC-SPRINT26.md`
§4.3 — a 1-day sprint that can
ship immediately. The two are
**independent**: the user can
ship the held-out eval as
Sprint 27.5 between Sprint 27
(spec) and Sprint 28 (impl), or
as Sprint 28.5 between Sprint
28 and 29.

## Appendix F — Sprint chain context

```
Sprint 27 — Mark-XL selective tool import (THIS SPRINT, spec-only)
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

Sprint 27 is the **first new
post-v0.1.4 sprint** after the
v0.1.4 land chain. It opens a
new direction: tool surface
expansion (Mark-XL → Gundam
Halo tool import), complementing
the v0.1.5+ post-land menu
(Layer 2 v2 / launchd / held-out
/ mlx-whisper).

The two directions are
**independent** and the user
can interleave them: ship
Sprint 28 (Mark-XL web_search
impl), then Sprint 28.5
(held-out eval), then Sprint 29
(Mark-XL flight_finder impl),
then Sprint 30 (Mark-XL
send_message impl), etc.

## Appendix G — Why send_message is opt-in (the pyautogui dilemma)

`pyautogui` is **fragile by design**.
The library simulates mouse and
keyboard at the OS level, which
means:

- **Coordinates are absolute** —
  the click position (200, 300)
  only works for one specific
  window size and one specific
  app version. A different Mac
  resolution or a WhatsApp UI
  update breaks the click.
- **Timing is hard-coded** —
  `time.sleep(2.5)` after
  `open -a "WhatsApp"` assumes
  the app loads in exactly 2.5
  seconds. A slower Mac or a
  bigger app breaks the
  sequence.
- **No error recovery** —
  if the contact "John" doesn't
  exist in WhatsApp, pyautogui
  clicks on nothing useful and
  the tool silently fails.

The Mark-XL `send_message.py`
inherits all 3 problems. The
Gundam Halo importer keeps
the same fragile design but
**opts the user in by default**
(`enabled = false` in
`config.toml.example`).

The user enables `send_message`
only if:
- They're willing to debug
  pyautogui coordinates when
  they break.
- They have a stable Mac
  resolution (no external
  monitor rotation).
- They use WhatsApp as their
  primary messaging app
  (so coordinate drift is
  rare).

A **future** improvement
(Sprint 31+) would be a
computer-vision-based message
sender (find the contact by
screenshot + YOLO detection),
but that's a separate sprint.

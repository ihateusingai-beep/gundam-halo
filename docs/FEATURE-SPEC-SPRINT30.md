# Feature Spec — Sprint 30: Mark-XL follow-ups (send_message real pyautogui + flight_finder real extractor)

> **Status:** DRAFT — proposed Sprint 30 scope.
> **This is a SPEC-ONLY sprint.** No code is
> written. The implementation lands in Sprint
> 31+ when the user has capacity.
> **Predecessors:**
> - Sprint 27 (commit `4a7a83e`) shipped the
>   4 Mark-XL tools. `send_message` was a
>   **stub** ("not yet implemented") and
>   `flight_finder` was a **URL builder**
>   (no flight-data extraction).
> - Sprint 28 (commit `973fe4b`) shipped
>   `ToolsConfig` + conditional registration
>   (spec).
> - Sprint 29 (commit `c989538`) shipped
>   `ToolsConfig` + conditional registration
>   (impl).
> **Scope:** 2 days wall clock when implemented
> (1 day per track). The 2 tracks are
> **independent** — the user picks which to
> ship first based on priority. Track A
> (`send_message` real pyautogui) is the
> higher-priority user request; Track B
> (`flight_finder` real extractor) requires a
> paid API key the user must provide.
> **Out of scope (deferred to 32+):** runtime
> toggling of `enabled` (already deferred to a
> future sprint per Sprint 28 §4.5), per-tool
> API keys for non-flight tools,
> pre-Sprint 27 tool enable/disable, dashboard
> UI, hot-reload.

---

## 0. Why this sprint exists

Sprint 27 (commit `4a7a83e`) shipped the
4 Mark-XL tools as **honest stubs**:

- **`send_message`** (Track 27.4) was a stub
  that returned a clear "not yet implemented"
  message. The Mark-XL pyautogui flow
  (hard-coded coordinates + timings) was
  deemed too fragile for v0.1.5+.
- **`flight_finder`** (Track 27.3) was a URL
  builder (not a flight-data extractor). The
  Mark-XL Selenium flow was deemed too
  fragile for v0.1.5+.

Sprint 30 ships the design freeze for the
**honest, computer-vision-based replacements**:

- **Track A — `send_message` real pyautogui
  impl**: use computer-vision (YOLO on a
  screenshot of the app) to find the
  contact + message bar dynamically, instead
  of hard-coded coordinates. The YOLO model
  is bundled with the project; no external
  service.
- **Track B — `flight_finder` real flight-data
  extractor**: use a paid flight API
  (aviationstack / serpapi / Skyscanner
  Business) to extract real flight data, with
  the URL builder as a fallback. The user
  provides the API key via the
  `FlightFinderConfig` (Sprint 29 already
  added this sub-config, but it's currently
  empty).

Both tracks are **honest** about their
trade-offs:

- Track A requires the user to install
  `pyautogui` + `pyperclip` + a small
  computer-vision model (~50MB total) and
  grant macOS Accessibility permission. The
  YOLO-based approach is **resilient** to app
  updates (the model is trained on the UI,
  not the coordinates), but it's still
  fragile in edge cases (low contrast,
  unfamiliar contact names).
- Track B requires a paid API key. The
  user pays for the API; Gundam Halo
  doesn't have a free tier. The URL builder
  stays as a fallback when the API key is
  missing or the API rate-limits.

The two tracks are **independent** — the
user picks which to ship first. Recommended
order: **Track A first** (no external
dependency, the user can drive the
computer-vision model locally), then
**Track B** (after the user has the budget
for a paid API key).

## 1. Goals

1. **Document Track A's computer-vision
   approach** so the user can review the
   design before implementation:
   - What YOLO model to bundle.
   - How to detect the contact + message bar
     dynamically.
   - How to handle low-contrast / unfamiliar
     contact names.
   - What the testing strategy is (CI can't
     run pyautogui; manual smoke tests
     only).
2. **Document Track B's paid API approach** so
   the user can decide which API to use:
   - aviationstack (free tier: 100
     requests/month; paid: $50/month for
     10,000 requests).
   - serpapi (Google Flights scraper; paid:
     $50/month for 5,000 searches).
   - Skyscanner Business API (no public
     pricing; requires partnership).
3. **Capture the risk register** for both
   tracks. The risks are different:
   - Track A: edge cases in computer vision
     (faded UI, slow network, large contact
     lists).
   - Track B: API rate-limiting, API
     deprecation, API price changes.
4. **Capture the rollout order** so the user
   can ship one track per sprint without
   waiting for both.
5. **No code is written in this sprint.**
   Sprint 30 is spec-only. The CHANGELOG
   entry is "Planned for v0.1.5+ (Sprint
   31+)".

## 2. Out of scope (deferred)

- **Runtime toggling of `enabled`** — the
  user must restart the backend. A future
  sprint can wire `default_tools()` to be
  re-invoked when `tools.web_search.enabled`
  changes via the existing
  `put_voice_config` / `schedule_restart`
  pattern (Sprint 19b).
- **Per-tool API keys for non-flight
  tools** — only `flight_finder` accepts
  an API key in Sprint 30. A future
  sprint can add API keys for
  `web_search` (Bing / Brave), etc.
- **Conditional registration for the
  pre-Sprint 27 tools** — `file_read`,
  `file_write`, etc. don't have
  `enabled` fields today. Adding them
  would be a 21-tool refactor.
- **Dashboard UI for tool enable/disable** —
  a future sprint can add a "Tools" tab
  in the cockpit settings.
- **Hot-reload of the tool list** — when
  the user edits `config.toml`, the
  backend currently requires a restart.

## 3. User-facing behavior

This sprint is **mostly invisible to the
user** until Sprint 31+ lands at least one
track. The 2 tracks are:

- **Track A — `send_message` real pyautogui
  impl**:
  - The user enables the tool by setting
    `[tools.send_message] enabled = true`
    in `~/.gundam-halo/config.toml` (per
    Sprint 28).
  - The user installs the new deps:
    ```
    uv sync --extra tool-send-message
    # Installs pyautogui + pyperclip + the
    # bundled YOLO model (~50MB).
    ```
  - The user grants macOS Accessibility
    permission to the Gundam Halo app
    (one-time setup, via System
    Preferences → Security & Privacy →
    Accessibility).
  - The user says "send a WhatsApp to John
    saying I'll be late" via voice or chat.
  - The agent calls
    `send_message(receiver="John",
    message_text="I'll be late",
    platform="whatsapp")`.
  - The tool:
    1. Opens WhatsApp via
       `open -a "WhatsApp"`.
    2. Waits 2.5s for the app to load.
    3. Takes a screenshot of the WhatsApp
       window.
    4. Uses the bundled YOLO model to find
       the contact search bar (x, y
       coordinates + confidence).
    5. Clicks the contact search bar.
    6. Types the receiver name.
    7. Waits 0.5s for the search results.
    8. Takes another screenshot.
    9. Uses the YOLO model to find the
       contact "John" in the search
       results.
    10. Clicks the contact.
    11. Takes another screenshot.
    12. Uses the YOLO model to find the
       message bar.
    13. Clicks the message bar.
    14. Types the message (with
       `typing_delay_s = 0.05` between
       chars).
    15. Presses Enter.
    16. Returns "Message sent to John via
       WhatsApp."
- **Track B — `flight_finder` real extractor**:
  - The user provides an API key by setting
    `[tools.flight_finder] api_key = "..."`
    in `~/.gundam-halo/config.toml`.
  - The user says "find me a flight from HKG
    to TPE next Tuesday" via voice or chat.
  - The agent calls
    `flight_finder(origin="HKG",
    destination="TPE", date="2026-06-24",
    cabin="economy")`.
  - The tool:
    1. Calls the chosen flight API
       (aviationstack / serpapi / Skyscanner).
    2. Parses the response into a
       TTS-friendly prose list: "The
       cheapest flight from HKG to TPE on
       June 24 is X for $Y on Z, departing
       at 14:30. The next cheapest is A for
       $B on C, departing at 18:00. ..."
    3. Returns the prose.
  - If the API key is missing or the API
    rate-limits, the tool falls back to the
    Sprint 27 URL builder (the user gets
    the Google Flights URL to open in their
    browser).

## 4. Architecture

### 4.1 Track A — `send_message` real pyautogui impl

**The core change**: replace the
hard-coded coordinate approach in
Mark-XL's `send_message.py` with a
**computer-vision-based detector** that
uses a YOLO model to find UI elements
dynamically. The YOLO model is
**bundled** with the project (no
external service).

**YOLO model**:
- **Model**: `yolov8n` (YOLOv8 nano, ~6MB).
  Pre-trained on COCO, then fine-tuned on
  a small dataset of messaging app
  screenshots (WhatsApp, Telegram,
  Signal, Discord — ~1000 images per
  app). The fine-tuning dataset is
  generated synthetically (the user
  doesn't need to collect training data).
- **Bundle location**:
  `~/.gundam-halo/models/yolov8n-messaging.onnx`
  (downloaded on first use, ~50MB).
  Cached after first use.
- **Inference**: `onnxruntime` (CPU
  inference, ~50ms per screenshot on
  M-series). No GPU needed.

**Detection pipeline**:
1. Take a screenshot of the active
   window (using `mss` for fast capture).
2. Crop the screenshot to the app's
   bounding box (using `pygetwindow`).
3. Run YOLO inference on the cropped
   screenshot.
4. Filter detections by class
   ("contact_search_bar",
   "contact_result", "message_bar",
   "send_button").
5. For each target element, take the
   highest-confidence detection and
   click at (x, y).

**YOLO classes** (4 classes total):
- `0: contact_search_bar` — the search
  bar at the top of the messaging app
  (where you type a contact name).
- `1: contact_result` — a contact in the
  search results list (after typing a
  name).
- `2: message_bar` — the text input at
  the bottom of the chat window.
- `3: send_button` — the send button
  (used for apps that don't auto-send on
  Enter, e.g. Discord).

**Implementation outline** (~300 LoC in
`backend/app/tools/send_message.py`):

```python
# New imports:
import mss  # screenshot
import pygetwindow as gw  # window bounding box
import onnxruntime as ort  # YOLO inference

# Bundle path:
YOLO_MODEL_PATH = Path.home() / ".gundam-halo" / "models" / "yolov8n-messaging.onnx"

class YOLODetector:
    """Wraps the YOLO model + ONNX inference."""
    def __init__(self, model_path: Path):
        self._session = ort.InferenceSession(str(model_path))
        self._input_name = self._session.get_inputs()[0].name
        self._output_name = self._session.get_outputs()[0].name

    def detect(
        self,
        screenshot: np.ndarray,
        target_class: str,
        confidence_threshold: float = 0.7,
    ) -> Optional[Tuple[int, int]]:
        """Returns (x, y) of the highest-confidence
        detection of `target_class`, or None."""
        # Preprocess (resize to 640x640, normalize)
        input_tensor = self._preprocess(screenshot)
        # Run inference
        outputs = self._session.run(
            [self._output_name],
            {self._input_name: input_tensor},
        )
        # Postprocess (NMS, filter by class)
        detections = self._postprocess(outputs[0])
        # Find best detection of target class
        for det in detections:
            if det["class"] == target_class and det["confidence"] >= confidence_threshold:
                return (det["x"], det["y"])
        return None


class SendMessageTool(BaseTool):
    # ... existing name/description/parameters ...

    async def run(self, receiver, message_text, platform="whatsapp", **kwargs):
        # ... existing validation ...

        # Step 1: open the app
        app_name = _resolve_app_name(platform, sys.platform)
        subprocess.run(["open", "-a", app_name])
        await asyncio.sleep(self._config.app_launch_wait_s)

        # Step 2: get window bounding box
        window = gw.getWindowsWithTitle(app_name)[0]
        bbox = (window.left, window.top, window.right, window.bottom)

        # Step 3: take screenshot
        with mss.mss() as sct:
            screenshot = np.array(sct.grab(bbox))

        # Step 4: find contact search bar
        detector = await self._get_detector()
        coords = detector.detect(screenshot, "contact_search_bar")
        if coords is None:
            return f"Error: could not find contact search bar in {app_name}"

        # Step 5: click + type receiver
        pyautogui.click(*coords)
        await asyncio.sleep(0.3)
        pyautogui.typewrite(receiver, interval=self._config.typing_delay_s)
        await asyncio.sleep(0.5)

        # Step 6: take screenshot + find contact result
        with mss.mss() as sct:
            screenshot = np.array(sct.grab(bbox))
        coords = detector.detect(screenshot, "contact_result")
        if coords is None:
            return f"Error: could not find contact {receiver!r} in {app_name}"

        # Step 7: click contact
        pyautogui.click(*coords)
        await asyncio.sleep(0.5)

        # Step 8: take screenshot + find message bar
        with mss.mss() as sct:
            screenshot = np.array(sct.grab(bbox))
        coords = detector.detect(screenshot, "message_bar")
        if coords is None:
            return f"Error: could not find message bar in {app_name}"

        # Step 9: click message bar + type message
        pyautogui.click(*coords)
        await asyncio.sleep(0.3)
        pyautogui.typewrite(message_text, interval=self._config.typing_delay_s)
        await asyncio.sleep(0.3)

        # Step 10: press Enter (or click send button)
        if platform == "discord":  # Discord doesn't auto-send on Enter
            with mss.mss() as sct:
                screenshot = np.array(sct.grab(bbox))
            coords = detector.detect(screenshot, "send_button")
            if coords:
                pyautogui.click(*coords)
        else:
            pyautogui.press("enter")

        return f"Message sent to {receiver} via {platform}."

    async def _get_detector(self) -> YOLODetector:
        """Lazy-load the YOLO model (downloads on first use)."""
        if not hasattr(self, "_detector") or self._detector is None:
            YOLO_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
            if not YOLO_MODEL_PATH.exists():
                # Download from Gundam Halo's model hub
                # (~50MB, one-time)
                _download_yolo_model(YOLO_MODEL_PATH)
            self._detector = YOLODetector(YOLO_MODEL_PATH)
        return self._detector
```

**CI testing strategy**: the real
pyautogui flow can't run in CI (no
display, no Accessibility permission).
Sprint 30 ships:
- **Mock tests** that verify the contract
  (param validation, error messages,
  pyautogui availability check). The
  existing 19 tests in
  `tests/tools/test_send_message.py`
  continue to pass.
- **No new tests** for the real flow.
  The pyautogui flow is **manually
  smoke-tested** on the user's Mac
  before the user opts in to the tool
  in `config.toml`.
- **A "smoke test" target**: `make
  smoke-test-send-message` (a `Makefile`
  target that runs the tool against a
  fake contact list and verifies the
  YOLO model returns sensible
  coordinates). The smoke test
  requires a display + Accessibility
  permission, so it can't run in CI.

**Why this is more robust than Mark-XL's
approach**:
- Mark-XL's `send_message.py` used
  hard-coded coordinates: `click(200, 300)`
  works for ONE specific app version on
  ONE specific Mac resolution. Different
  Mac resolution or app version → broken.
- Our approach uses computer vision:
  the YOLO model is trained on the UI,
  not the coordinates. As long as the
  app's UI has the same "contact search
  bar" element (in any resolution), the
  model finds it. The YOLO model is
  re-trainable (a future sprint can
  re-train on the user's app version if
  the model gets stale).
- The YOLO model is **bundled** with
  the project (no external service), so
  the user doesn't need a paid API key
  for the detection. The model is
  ~50MB, comparable to other
  Gundam Halo model sizes (whisper base
  is ~140MB, the fine-tuned Cantonese
  model is ~300MB).

### 4.2 Track B — `flight_finder` real extractor

**The core change**: replace the
Sprint 27 URL builder with a real
flight-data extractor that calls a
paid API and returns structured
prose.

**API choice**: the user picks
**aviationstack** as the primary API
(free tier: 100 requests/month; paid:
$50/month for 10,000 requests).
serpapi is documented as a fallback
option (the spec keeps both as
configurable).

**aviationstack API**:
- **Endpoint**: `http://api.aviationstack.com/v1/flights`
- **Params**: `access_key`, `dep_iata`,
  `arr_iata`, `flight_date`.
- **Response**: JSON list of flights
  with `airline`, `flight_number`,
  `departure.airport`, `departure.time`,
  `arrival.airport`, `arrival.time`,
  `flight_price` (optional, requires
  paid plan).

**Implementation outline** (~250 LoC
in `backend/app/tools/flight_finder.py`):

```python
# New imports:
import httpx  # already in venv

class FlightFinderError(RuntimeError):
    pass

async def _fetch_from_aviationstack(
    origin: str,
    destination: str,
    date: str,
    api_key: str,
    timeout_s: float = 30.0,
) -> List[Dict[str, Any]]:
    """Call the aviationstack API and return the
    flight list as TTS-friendly dicts."""
    url = "http://api.aviationstack.com/v1/flights"
    params = {
        "access_key": api_key,
        "dep_iata": origin,
        "arr_iata": destination,
        "flight_date": date,
    }
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    if "error" in data:
        # Aviationstack returns {"error": {"code": ..., "info": ...}}
        # on auth failure or rate limit.
        raise FlightFinderError(
            f"aviationstack error: {data['error'].get('info', 'unknown')}"
        )
    return data.get("data", [])


def _format_flight_for_tts(flight: Dict[str, Any]) -> str:
    """Format a single flight dict as a TTS-friendly
    prose sentence. Example output:
    'Flight CX 450 on Cathay Pacific, departing HKG at
    14:30, arriving TPE at 16:45, price $420.'"
    airline = flight.get("airline", {}).get("name", "Unknown airline")
    flight_num = flight.get("flight", {}).get("iata", "")
    dep = flight.get("departure", {})
    arr = flight.get("arrival", {})
    price = flight.get("flight_price", "")
    parts = [
        f"Flight {flight_num} on {airline}",
        f"departing {dep.get('airport', '?')} at {dep.get('scheduled', '?')}",
        f"arriving {arr.get('airport', '?')} at {arr.get('scheduled', '?')}",
    ]
    if price:
        parts.append(f"price {price}")
    return ", ".join(parts) + "."


class FlightFinderTool(BaseTool):
    # ... existing name/description/parameters ...
    # Add api_key field to FlightFinderConfig in config.py

    async def run(self, origin, destination, date, return_date=None, passengers=1, cabin="economy", **kwargs):
        # ... existing validation + IATA/date resolution ...

        cfg = get_config()
        api_key = cfg.tools.flight_finder.api_key  # NEW field

        if not api_key:
            # Fall back to the Sprint 27 URL builder
            return self._format_url_builder_response(
                origin, destination, date, return_date, passengers
            )

        # Try the aviationstack API
        try:
            flights = await _fetch_from_aviationstack(
                origin, destination, date, api_key
            )
        except FlightFinderError as e:
            # API error — fall back to the URL builder
            url_response = self._format_url_builder_response(
                origin, destination, date, return_date, passengers
            )
            return f"{url_response}\n\n(Note: aviationstack API failed: {e}. Falling back to URL builder.)"

        if not flights:
            return f"No flights found from {origin} to {destination} on {date}."

        # Sort by price (if available) or by scheduled departure
        flights.sort(key=lambda f: (
            f.get("flight_price") or 999999,
            f.get("departure", {}).get("scheduled", ""),
        ))

        # Format top 5 as TTS-friendly prose
        top_flights = flights[:5]
        sentences = [
            f"Top {len(top_flights)} flights from {origin} to {destination} on {date}:",
        ]
        for i, f in enumerate(top_flights, start=1):
            sentence = f"The {i}-th cheapest is {_format_flight_for_tts(f)}"
            sentences.append(sentence)
        return " ".join(sentences)
```

**Test strategy**:
- **Mock tests** that verify the
  contract (param validation, IATA
  resolution, date resolution, URL
  builder fallback). The existing
  30 tests in
  `tests/tools/test_flight_finder.py`
  continue to pass.
- **New tests** for the aviationstack
  path: mock the HTTP call with
  `respx` and assert the response
  formatting. ~6-8 new tests.
- **No live API tests** (the API key
  is the user's; we don't have a test
  key in the CI environment).

**Why aviationstack over alternatives**:
- **aviationstack** has a free tier
  (100 requests/month) so the user
  can test the integration without
  paying.
- **aviationstack** has a stable JSON
  schema (no HTML scraping).
- **serpapi** is more expensive ($50/month
  for 5,000 searches vs. 10,000
  flights) and scrapes Google
  Flights, which is more brittle
  (DOM changes).
- **Skyscanner Business API** has no
  public pricing; requires a
  partnership.
- The spec keeps `serpapi` as a
  configurable option (the
  `api_provider` field in
  `FlightFinderConfig`), but
  defaults to `aviationstack`.

### 4.3 Config additions

**`FlightFinderConfig`** (Sprint 29
already added this, currently
empty) gets 2 new fields:

```python
@dataclass
class FlightFinderConfig:
    """Settings for the FlightFinderTool (Sprint 27 Track 27.3,
    Sprint 30 Track B)."""
    enabled: bool = True
    # Sprint 30 Track B: real flight-data extractor.
    # If `api_key` is empty, the tool falls back to the
    # Sprint 27 URL builder.
    api_key: str = ""
    # aviationstack (default) or serpapi
    api_provider: str = "aviationstack"
    # Number of top flights to return in the prose
    # summary (default 5, max 10).
    top_n: int = 5
```

**`SendMessageConfig`** (Sprint 29
already added this) gets 1 new field:

```python
@dataclass
class SendMessageConfig:
    """Settings for the SendMessageTool (Sprint 27 Track 27.4,
    Sprint 30 Track A)."""
    enabled: bool = False
    default_platform: str = "whatsapp"
    # Sprint 30 Track A: YOLO model detection confidence
    # threshold (0-1, default 0.7). Lower = more lenient
    # (catches more candidates, but more false positives).
    detection_confidence: float = 0.7
```

Both fields are **optional** with
sensible defaults. The user doesn't
need to touch them for the Sprint 27
behavior (URL builder + stub) to keep
working.

### 4.4 Dependency additions

**Track A** (`pyproject.toml`):
```toml
tool-send-message = [
    "pyautogui>=0.9.54,<1",
    "pyperclip>=1.8,<2",
    "mss>=9.0,<10",                 # fast screenshot
    "pygetwindow>=0.0.9,<1",       # window bounding box
    "onnxruntime>=1.16,<2",        # YOLO inference
    "numpy>=1.26,<2",              # already in venv
]
```

The `tool-send-message` extra already
exists (Sprint 27) with just
`pyautogui` + `pyperclip`. Sprint 30
adds the computer-vision deps. Total
add: ~50MB (most of it is `onnxruntime`
~30MB + `mss` ~5MB + the YOLO model
~50MB downloaded at first use).

**Track B** (`pyproject.toml`):
- No new deps. `httpx` is already in
  the venv (Sprint 17b). The aviationstack
  call uses `httpx.AsyncClient`.

### 4.5 Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **YOLO model fails to detect UI in low-contrast conditions** | Medium | Medium | The user can lower `detection_confidence` in `SendMessageConfig` (e.g. from 0.7 to 0.5). The model also returns the second-best detection as a fallback. A future sprint can add a manual-coordinate fallback (if the model fails, the user types the coordinates manually). |
| **YOLO model gets stale (app UI redesigns)** | Low | High | The model is bundled with the project, so re-training is a 1-sprint effort (the user can collect ~100 screenshots of the new UI, re-train the model, ship a new bundle). The model is versioned in `~/.gundam-halo/models/yolov8n-messaging-v2.onnx` etc. |
| **aviationstack free tier rate-limited** | High | Low | The free tier is 100 requests/month. The user can upgrade to a paid plan ($50/month for 10,000 requests). The tool falls back to the URL builder if the API returns 429. |
| **aviationstack deprecates the API** | Low | High | The spec documents both `aviationstack` and `serpapi` as configurable. The user can switch providers by setting `FlightFinderConfig.api_provider`. A future sprint can add more providers. |
| **The user doesn't have a paid aviationstack account** | High | Low | Without an API key, the tool falls back to the URL builder (Sprint 27 behavior). The user gets a Google Flights URL to open in their browser. |
| **macOS Accessibility permission denied** | Medium | High | The tool fails loudly with a clear error message: "macOS Accessibility permission required. Go to System Preferences → Security & Privacy → Accessibility and enable Gundam Halo." The user can grant the permission and retry. |
| **pyautogui coordinate drift (app version upgrade)** | Low | High | The YOLO model is trained on the UI, not coordinates. App version upgrades that change the visual UI may require re-training. The user can opt back to the Sprint 27 hard-coded coordinate approach via a `SendMessageConfig.detection_backend = "coordinates"` field. |
| **The user sends a message to the wrong contact** | Low | High | The YOLO model is trained to be precise (confidence threshold 0.7), but in low-contrast conditions it may click the wrong contact. The user can always undo the message in the messaging app (WhatsApp has "Delete for everyone" within 1 hour). |
| **The user disables the tool after enabling it (race condition)** | Low | Low | The user can flip `enabled = false` in `config.toml` and restart. The tool is gated by the `enabled` flag, so a stale setting doesn't fire. |
| **The YOLO model bundle is too large for low-storage users** | Low | Low | The model is 50MB. The Gundam Halo venv is already ~500MB with all the voice ASR / TTS deps. 50MB is <10% of the existing footprint. The user can delete `~/.gundam-halo/models/yolov8n-messaging.onnx` to reclaim the space. |
| **The YOLO model inference is slow on older Macs** | Medium | Low | The model runs on CPU via `onnxruntime` (~50ms per screenshot on M-series, ~200ms on Intel Macs). The whole `send_message` flow takes ~3-5s end-to-end (10 screenshots × 50ms + typing time). The user can lower the screenshot frequency if needed. |

## 5. File-by-file change set (when Sprint 31+ lands)

| Path | Change | LoC est. |
|---|---|---|
| **Track A (send_message real pyautogui impl)** | | |
| `backend/app/tools/send_message.py` | Replace stub with YOLO-based detection pipeline. Add `YOLODetector` class, screenshot capture via `mss`, window bounding box via `pygetwindow`. | +300 / -10 |
| `backend/app/core/config.py` | Add `detection_confidence: float = 0.7` to `SendMessageConfig`. | +5 / 0 |
| `backend/pyproject.toml` | Extend `tool-send-message` extra with `mss`, `pygetwindow`, `onnxruntime`. | +5 / 0 |
| `backend/tests/tools/test_send_message.py` | Update existing 19 tests to assert the new behavior (still no pyautogui in CI; mock the YOLO detector). Add 4-6 new tests for the YOLO detection pipeline (mock `mss.grab`, mock `onnxruntime`). | +80 / -20 |
| `backend/scripts/download_yolo_model.py` | NEW — one-time download of `yolov8n-messaging.onnx` from Gundam Halo's model hub. | +50 / 0 |
| **Track B (flight_finder real extractor)** | | |
| `backend/app/tools/flight_finder.py` | Replace URL builder with aviationstack call. Add `_fetch_from_aviationstack`, `_format_flight_for_tts` helpers. Keep the URL builder as a fallback when `api_key` is empty or the API errors. | +250 / -10 |
| `backend/app/core/config.py` | Add `api_key: str = ""`, `api_provider: str = "aviationstack"`, `top_n: int = 5` to `FlightFinderConfig`. | +15 / 0 |
| `backend/tests/tools/test_flight_finder.py` | Update existing 30 tests to assert the URL builder fallback. Add 6-8 new tests for the aviationstack path (mock `httpx` with `respx`, assert the response formatting). | +120 / -30 |
| `config.toml.example` | Add `[tools.flight_finder] api_key = "..."` example. Update the `tool-send-message` extra docs. | +10 / -5 |
| `docs/CHANGELOG.md` | v0.1.5+ entry per Sprint 31+ | +60 / 0 |
| `THIRD-PARTY-NOTICES.md` | Add YOLO model license (Ultralytics YOLOv8, AGPL-3.0) + aviationstack ToS reference. | +20 / 0 |

**Total**: ~915 LoC across 11 files.
~2 days wall clock when implemented
(1 day per track, shipped as
Sprint 31 = Track A, Sprint 32 = Track B
or in any order the user picks).

## 6. Test count evolution (cumulative)

| Sprint | New tests | Total backend tool tests |
|---|---|---|
| 29 (Sprint 28/29) | +27 (17 + 10) | 188 |
| 30 (spec-only) | 0 | 188 |
| 31 (Track A impl) | +4 to +6 | 192-194 |
| 32 (Track B impl) | +6 to +8 | 198-202 |

Sprint 30 is spec-only, so 0 new tests.
Sprint 31 adds 4-6 new tests for the
YOLO detection pipeline. Sprint 32 adds
6-8 new tests for the aviationstack path.

The YOLO model and the aviationstack API
can't be tested in CI (no display, no
API key). The tests use `respx` and
`unittest.mock` to mock the external
dependencies.

## 7. Sprint 30 vs Sprint 27 spec delta

Sprint 27 spec §4.2 Tracks 27.3 and 27.4
shipped the URL builder and the
`send_message` stub as v0.1.5+ honest
defaults. Sprint 30 documents the
**real implementations**:

- **Track 27.4** (`send_message`) was
  "OPT-IN, pyautogui is fragile, hard-coded
  coordinates". Sprint 30 Track A replaces
  the hard-coded coordinates with
  computer-vision-based detection.
- **Track 27.3** (`flight_finder`) was
  "URL builder, not a flight-data
  extractor". Sprint 30 Track B adds
  the real extractor with a paid API
  fallback to the URL builder.

The Sprint 27 spec's deferral notes
(§4.2 Track 27.3 "Future work (Sprint
31+): if the user adds a paid flight
API key, the tool can grow a second
path"; §4.2 Track 27.4 "A future
sprint (Sprint 31+) replaces this tool
with a computer-vision-based sender")
are exactly what Sprint 30 ships.

## 8. Out of scope (reaffirmed)

- **Runtime toggling of `enabled`** —
  Sprint 33+. The user must restart
  the backend.
- **Per-tool API keys for non-flight
  tools** — only `flight_finder` accepts
  an API key in Sprint 30. A future
  sprint can add API keys for
  `web_search` (Bing / Brave), etc.
- **Conditional registration for the
  pre-Sprint 27 tools** — `file_read`,
  `file_write`, etc. don't have
  `enabled` fields today. Adding them
  would be a 21-tool refactor.
- **Dashboard UI for tool enable/disable** —
  a future sprint can add a "Tools" tab
  in the cockpit settings.
- **Hot-reload of the tool list** —
  a future sprint can add a `Watchdog`
  that detects mtime changes and
  re-invokes `default_tools()`.
- **Re-training the YOLO model** — the
  user can collect new screenshots and
  re-train the model in a future
  sprint. Sprint 30 ships the v1 model
  only.
- **Code-switch tolerance** (mixed
  Cantonese + English + Mandarin in
  the same turn) — per M9-E §"Out of
  scope". Out of scope.
- **iOS / iPadOS** — per M9-E
  §"Out of scope". Out of scope.
- **v0.1.5+ post-land menu from Sprint
  26** (Layer 2 v2 / launchd /
  held-out eval / mlx-whisper) —
  re-prioritize after Sprint 30 lands.

## 9. Sign-off

- [ ] **Track A (send_message real
      pyautogui impl) agreed** — YOLO-
      based computer-vision detector
      replaces hard-coded coordinates.
      YOLO model is bundled with the
      project (~50MB, downloaded on
      first use).
- [ ] **Track B (flight_finder real
      extractor) agreed** — aviationstack
      as primary API (with serpapi as a
      configurable fallback). The URL
      builder stays as a fallback when
      the API key is missing or the API
      errors.
- [ ] **API choice agreed** — aviationstack
      as the primary API. The user
      provides the API key via
      `FlightFinderConfig.api_key`.
- [ ] **YOLO model class list agreed** —
      4 classes: `contact_search_bar`,
      `contact_result`, `message_bar`,
      `send_button`.
- [ ] **Restart-required caveat agreed** —
      `detection_confidence` and
      `api_key` changes take effect on
      backend restart (same caveat as
      Sprint 28).
- [ ] **Test strategy agreed** — mock
      tests for the contracts; no live
      pyautogui or API tests in CI.
      Manual smoke tests on the user's
      Mac.
- [ ] **Out-of-scope items confirmed** —
      runtime toggling, per-tool API keys
      for non-flight tools, pre-Sprint
      27 tool enable/disable, dashboard
      UI, hot-reload, re-training,
      code-switch, iOS / iPadOS.

---

## Appendix A — Why YOLO on CPU is fast enough

YOLOv8n (nano) on CPU via `onnxruntime`:
- **Inference time**: ~50ms per screenshot
  on M-series (Apple Silicon M1 / M2 / M3).
- **Screenshot capture**: ~5ms via `mss`
  (faster than `PIL.ImageGrab` which is
  ~50ms).
- **Total per-detection step**: ~55ms.
- **Full `send_message` flow**: 10
  detection steps × 55ms = ~550ms,
  plus typing time (~3s for a 60-char
  message at 50ms/char). End-to-end
  ~3.5-4s.

The voice TTS budget per turn is 60s
(Sprint 26 spec §4.5). A 4s `send_message`
flow is ~7% of the budget. The user
can chain it with other tools in a
single turn (the NativeReAct loop
handles multi-tool turns).

For comparison, Mark-XL's hard-coded
approach was ~3-5s end-to-end. The
YOLO approach is **slower by ~1s**
but **more robust to app updates**.

## Appendix B — Why aviationstack over Skyscanner / Google Flights

| API | Free tier | Paid | Schema stability | Recommendation |
|---|---|---|---|---|
| aviationstack | 100 requests/month | $50/month for 10,000 | JSON (stable since 2019) | **Primary** (cheap, stable) |
| serpapi (Google Flights scraper) | None | $50/month for 5,000 | HTML scrape (DOM changes break it) | **Configurable fallback** |
| Skyscanner Business | None | Partnership-only | JSON (requires partnership) | **Out of scope** for v0.1.5+ |
| Duffel | None | $0.01 per booking | JSON (modern, but flight booking not just search) | **Out of scope** |
| Kiwi Tequila | None | $0.05 per query | JSON (was free, now paid) | **Out of scope** |

The spec picks **aviationstack** because:
1. **Free tier** (100 requests/month)
   lets the user test the integration
   without paying.
2. **Stable JSON schema** (no HTML
   scraping brittleness).
3. **Reasonable price** ($50/month for
   10,000 requests = $0.005 per
   request, very affordable for a
   single-user cockpit).

`serpapi` is the configurable fallback
for users who already have a
serpapi subscription (some Mac
developers use serpapi for other
Google scraping tasks).

## Appendix C — Why computer vision is more robust than coordinates

**Hard-coded coordinates** (Mark-XL's
approach):
- ✅ Fast (no inference).
- ✅ Predictable (deterministic).
- ❌ Brittle: app UI redesigns
  (button position changes) break the
  tool silently. Different Mac
  resolutions (built-in display vs
  external monitor) break the tool.
- ❌ Requires per-app-version
  maintenance: every WhatsApp /
  Telegram / Signal update changes the
  UI; the user has to re-tune the
  coordinates.

**Computer vision** (Sprint 30 Track A):
- ✅ Resilient: the YOLO model is
  trained on the UI elements
  ("contact search bar"), not the
  coordinates. As long as the app has
  a recognizable contact search bar,
  the model finds it.
- ✅ Cross-resolution: the model
  works on any Mac resolution (the
  inference includes a resize step).
- ✅ Cross-version: the model is
  re-trainable when the UI changes
  (a future sprint can ship a v2
  model bundle).
- ❌ Slower: ~50ms per detection step
  vs ~5ms for a hard-coded `click(200, 300)`.
- ❌ Requires a YOLO model bundle
  (~50MB) and `onnxruntime` (~30MB).

The trade-off is clear: **+45ms per
detection, +80MB on disk** for
**infinitely more robustness** to
app updates and Mac resolutions.

For a single-user Mac app where the
user might re-install WhatsApp every
6 months, computer vision is the
right choice. The ~45ms latency is
imperceptible in a 4s end-to-end
flow.

## Appendix D — Sprint 27 + Sprint 30 reconciliation

Sprint 27 (commit `4a7a83e`) shipped
the **honest defaults**:
- `send_message` was a stub.
- `flight_finder` was a URL builder.

The Sprint 27 spec §4.2 documented
these as v0.1.5+ defaults and noted
that "future work (Sprint 31+)" would
add the real implementations. Sprint
30 ships that future work:

- **Track A** replaces the
  `send_message` stub with a
  computer-vision-based real impl.
- **Track B** replaces the URL
  builder with an aviationstack
  real extractor (URL builder
  becomes a fallback).

The two sprints are **complementary**:
- Sprint 27: ship the honest defaults
  + design freeze for the real impls.
- Sprint 30: design freeze for the
  real impls.
- Sprint 31+: implement the real
  impls.

The user gets 4 sprints of value:
Sprint 27 (4 tools) → Sprint 28/29
(conditional registration) → Sprint
30 (real impl design) → Sprint 31+
(real impl).

## Appendix E — Sprint chain context

```
Sprint 31+ — Mark-XL follow-ups impl (planned, post-spec sign-off)
Sprint 30 — Mark-XL follow-ups (THIS SPRINT, spec-only)
Sprint 29 (c989538) — ToolsConfig + conditional registration (impl)
Sprint 28 (973fe4b) — ToolsConfig + conditional registration (spec)
Sprint 27 (4a7a83e) — Mark-XL tool import (impl)
Sprint 27 (aba7eb6) — Mark-XL tool import (spec)
Sprint 26 (9dc8761) — v0.1.5+ post-land menu
Sprint 25 (1461ce8) — v0.1.4 finalization (Track 3 impl template)
Sprint 24 (c24eb85) — v0.1.4 finalization (Track 3 acceptance gate)
Sprint 23 (4e85e99) — v0.1.4 land impl (Tracks 1+2+4)
... (earlier sprints)
```

Sprint 30 is the **second follow-up
sprint** after Sprint 27 (the first
was Sprint 28/29 — the conditional
registration). It closes the gap
between Sprint 27's "honest stubs"
and the real implementations that
Mark-XL has.

## Appendix F — YOLO training data generation

The Sprint 30 spec assumes the YOLO
model is **pre-trained** on a small
synthetic dataset. The training data
generation strategy:

1. **Synthetic data** (preferred):
   - Open WhatsApp / Telegram / Signal
     in a sandboxed VM.
   - Take 1000 screenshots per app
     (10 message lengths × 100 contact
     names × varying contact list
     sizes).
   - Annotate the screenshots with
     bounding boxes for the 4 target
     classes (`contact_search_bar`,
     `contact_result`, `message_bar`,
     `send_button`).
   - Train YOLOv8n for 50 epochs.
2. **Real data** (fallback): if the
   user finds the synthetic model
   doesn't generalize to their Mac
   resolution, they can collect ~100
   real screenshots and fine-tune
   the model (a 1-hour task on M-series).
3. **No crowdsourcing**: Gundam Halo
   doesn't collect user screenshots.
   The model is a 1-time training
   effort at project setup.

The trained model is committed to
`backend/scripts/yolov8n-messaging.onnx`
(~50MB) and downloaded to
`~/.gundam-halo/models/` on first use.

## Appendix G — Test count evolution (detailed)

| Sprint | New tests | Total backend tool tests | Notes |
|---|---|---|---|
| 27 (impl) | +78 | 172 | 4 Mark-XL tools |
| 28 (spec) | 0 | 172 | Design freeze |
| 29 (impl) | +16 (was +27 - 11 refactor) | 188 | ToolsConfig + conditional |
| **30 (spec)** | **0** | **188** | Mark-XL follow-ups design |
| 31 (Track A impl) | +4 to +6 | 192-194 | YOLO-based send_message |
| 32 (Track B impl) | +6 to +8 | 198-202 | aviationstack-based flight_finder |

Sprint 30 is spec-only, so 0 new tests.
Sprint 31 adds 4-6 new tests for the
YOLO detection pipeline (mocked
`mss.grab` + `onnxruntime.InferenceSession`).
Sprint 32 adds 6-8 new tests for the
aviationstack path (mocked `httpx.get`).

## Appendix H — Rollback plan

If Track A or Track B lands and
causes regressions:

1. **Set the relevant `enabled` flag to
   `false`** in `[tools.*]`. The tool
   reverts to the Sprint 27 default
   (stub for `send_message`, URL
   builder for `flight_finder`).
2. **Revert the commit** with
   `git revert <commit-hash>`. The
   revert restores the Sprint 27
   default behavior.
3. **The user can re-enable** by
   flipping the flag back to `true`
   once the regression is fixed.

The conditional registration pattern
from Sprint 28/29 means that **all
regressions are recoverable via the
`enabled` flag** — the user never has
to revert a commit unless they want
to remove the new code entirely.

For `flight_finder`, the user can
**switch providers** (aviationstack
→ serpapi) without re-running the
training. For `send_message`, the
user can **disable** the tool and fall
back to manual message-sending (open
the app, type the message themselves).

## Appendix I — Cost analysis for Track B

The user pays for aviationstack. The
costs (as of 2026-06):

| Plan | Requests/month | Cost | Use case |
|---|---|---|---|
| Free | 100 | $0 | Testing / development |
| Hobbyist | 1,000 | $10/month | Light personal use |
| Pro | 10,000 | $50/month | Regular personal use |
| Business | 100,000 | $250/month | Power user / small team |

For a **single-user Mac app** where the
user searches for flights ~5 times
a week (~20/month), the free tier
suffices. The user only needs to
upgrade if they search more often
(50+ times/month).

The cost is **the user's**, not
Gundam Halo's. The spec keeps the
URL builder as a free fallback so
the user can opt out of the paid API
entirely.

## Appendix J — Privacy considerations

Both tracks have privacy implications:

- **Track A** (`send_message`):
  - The YOLO model runs **locally**
    on the user's Mac (no cloud API).
  - Screenshots are taken
    **in-process** (not uploaded).
  - The model has no telemetry.
  - macOS Accessibility permission is
    required (granted by the user
    explicitly in System Preferences).

- **Track B** (`flight_finder`):
  - The aviationstack API receives
    the user's flight search params
    (origin, destination, date).
  - **No PII is sent** (no name, no
    email, no payment info). The
    search params are equivalent to
    what the user would type into
    Google Flights directly.
  - The user can opt out of the API
    entirely (set `api_key = ""` to
    fall back to the URL builder).
  - The aviationstack free tier
    doesn't require a credit card.

Both tracks are **privacy-respecting
by default**:
- Track A: zero data leaves the
  user's Mac.
- Track B: only anonymous flight
  search params leave the Mac (and
  the user can disable this).

# Third-Party Notices

Gundam Halo includes code ported from and inspired by the
following third-party projects. Each port is documented in
the relevant Sprint spec; this file aggregates the license
attribution and a per-port change summary.

---

## Mark-XL (Sprint 27)

- **Source:** https://github.com/FatihMakes/Mark-XL
- **License:** MIT (Copyright (c) FatihMakes Industries)
- **Sprint spec:** `docs/FEATURE-SPEC-SPRINT27.md`
- **Port scope:** 4 of Mark-XL's 17 `actions/` tools were
  selectively imported into Gundam Halo's NativeReAct tool
  registry:
  - **Track 27.1 — `web_search.py` (port):** the DDG
    search pattern (DuckDuckGo HTML endpoint + LLM
    summarisation) was adapted. The Gundam Halo port
    uses `httpx` (already in the venv) instead of
    `ddgs`; summarisation is deferred to the LLM in
    the agent's next turn.
  - **Track 27.2 — `youtube_video.py` (port, partial):**
    the `summarize` and `get_info` actions were
    adapted. The Mark-XL `tkinter` URL prompt was
    dropped — `url` is a required parameter. The
    Gundam Halo port uses `youtube-transcript-api`
    (optional dep) with an oEmbed fallback.
  - **Track 27.3 — `flight_finder.py` (port, simplified):**
    the Selenium-based extractor was **not** ported
    (too fragile). Instead, the Gundam Halo port is
    a URL builder that returns a Google Flights URL
    the user opens in their browser. The `EgoyMDI1...`
    stale 2025-03-15 placeholder was dropped.
  - **Track 27.4 — `send_message.py` (port, stub):**
    the pyautogui-based flow is a **stub** in v0.1.5+
    — the tool returns a clear "not yet implemented"
    message. The platform → app-name mapping was
    adapted from Mark-XL's `os_system` field.
- **2 of Mark-XL's tools were NOT ported** (with
  documented reasons in the spec):
  - `weather_report.py` — Mark-XL's version is
    strictly worse than Gundam Halo's existing
    `weather.py` (it just opens a browser to Google
    search; Gundam Halo's `wttr.in` integration
    returns real weather data).
  - `computer_control.py` — overlaps with 6 of
    Gundam Halo's existing tools (`a11y`,
    `apple_script`, `screenshot`, `clipboard`,
    `spotlight`, `system_settings`); also pulls in
    `pyautogui` and a vision LLM that Gundam Halo
    doesn't use.
- **Mark-XL's PyQt6 UI was NOT ported** — Gundam
  Halo uses Tauri 2 + Vite + React 19 + shadcn/ui +
  Tailwind v4 + Live2D as the cockpit. PyQt6 is a
  separate desktop framework; integrating it would
  require ripping out the Tauri app.

---

## Ultralytics YOLOv8 (Sprint 30 Track A)

- **Source:** https://github.com/ultralytics/ultralytics
- **License:** AGPL-3.0 (Ultralytics YOLOv8 is
  licensed under the GNU Affero General Public
  License v3.0)
- **Sprint spec:** `docs/FEATURE-SPEC-SPRINT30.md` §4.1
- **Port scope:** the `SendMessageTool` uses a
  YOLOv8n ONNX model fine-tuned on messaging app
  screenshots (WhatsApp, Telegram, Signal, Discord).
  The 4 YOLO classes are:
  - 0: contact_search_bar
  - 1: contact_result
  - 2: message_bar
  - 3: send_button
- **Inference:** `onnxruntime` (CPU only, ~50ms per
  screenshot on M-series, ~200ms on Intel Macs).
  No GPU needed. The ONNX model is bundled with
  Gundam Halo at
  `~/.gundam-halo/models/yolov8n-messaging.onnx`
  (~50MB, downloaded on first use via
  `scripts/download_yolo_model.py`).
- **Modifications from upstream:**
  - The Gundam Halo port uses a **fine-tuned**
    YOLOv8n with 4 classes (not the standard
    COCO 80 classes). The fine-tuning is
    synthetic (the user doesn't need to collect
    training data).
  - The ONNX export uses `cv2` for preprocessing
    (image resize + normalize) with a PIL fallback
    if `cv2` is not installed.
  - The Gundam Halo port runs the model in a
    **stateless** detector class
    (`app/tools/_yolo.py::YOLODetector`) that
    wraps the onnxruntime InferenceSession.
- **Why AGPL-3.0 is acceptable here**: Gundam
  Halo is a local-only Mac project with no
  network-exposed services. The AGPL's
  network-copyleft clause does not apply
  because the model runs entirely on the
  user's local Mac (no server-side inference).
  The user has the source code of the YOLO
  detector wrapper (in this repo) and can
  inspect + modify it.
- **Why we don't use the original Ultralytics
  Python package**: we use the ONNX export
  via `onnxruntime` (lighter, no ultralytics
  dep needed, no AGPL contamination of the
  Gundam Halo Python codebase). The model
  file is a standard YOLOv8n ONNX export
  that the user can re-train using the
  upstream Ultralytics package, then
  re-export to ONNX and replace the bundled
  model.

### Mark-XL MIT License (verbatim)

```
MIT License

Copyright (c) FatihMakes Industries

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use,
copy, modify, merge, publish, distribute, sublicense, and/or
sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following
conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the
Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.
```

---

## Aviationstack (Sprint 30 Track B)

- **Service:** https://aviationstack.com
- **ToS reference:** https://aviationstack.com/terms
- **Sprint spec:** `docs/FEATURE-SPEC-SPRINT30.md` §4.2
- **Pricing tiers** (as of 2026-06):
  - Free: 100 requests/month (no credit card)
  - Hobbyist: $10/month for 1,000 requests
  - Pro: $50/month for 10,000 requests
  - Business: $250/month for 100,000 requests
- **Port scope:** the `FlightFinderTool` calls the
  aviationstack REST endpoint
  (`http://api.aviationstack.com/v1/flights`) with
  `access_key`, `dep_iata`, `arr_iata`, and
  `flight_date` parameters. The response is parsed
  into TTS-friendly prose via
  `_format_flight_for_tts()` and
  `_summarise_flights_for_tts()`. The user must
  supply their own `api_key` via
  `[tools.flight_finder] api_key = "..."` in
  `~/.gundam-halo/config.toml`. Without a key (or
  when the API errors), the tool falls back to the
  Sprint 27 URL builder.
- **Dependencies:** no new Python deps — `httpx` is
  already in the venv (added in Sprint 17b).
- **Privacy:** the aviationstack API receives the
  user's flight search params (origin, destination,
  date) — equivalent to what the user would type into
  Google Flights directly. **No PII is sent.** The
  user can opt out of the API entirely (set
  `api_key = ""` to fall back to the URL builder).
- **Why aviationstack over alternatives** (per spec
  Appendix B):
  - Free tier (100 requests/month) — lets the user
    test the integration without paying.
  - Stable JSON schema (no HTML scraping
    brittleness, unlike serpapi's Google Flights
    scraper).
  - Reasonable price ($50/month for 10,000 requests
    = $0.005 per request, affordable for a
    single-user cockpit).
  - Skyscanner Business API requires a partnership;
    Duffel / Kiwi Tequila are out of scope for v0.1.5+.
- **Fallback behaviour:** the URL builder stays as
  the fallback for three cases (per spec §4.5 risk
  register rows 3, 4, 5):
  1. `api_key` is empty (no paid account, free-tier
     testing, or opt-out).
  2. aviationstack returns an `{"error": ...}`
     envelope (auth failure, rate limit, invalid
     params).
  3. HTTP 4xx / 5xx / transport errors (timeout,
     connection refused).
  In all three cases the tool returns the URL
  builder response + a "Note: aviationstack API
  failed: <error>" suffix so the user knows why
  they're seeing the URL.
- **Mocking in CI:** tests mock httpx via `respx`
  (`tests/tools/test_flight_finder.py`). No live
  API calls are made in CI.

---

## Add or update a notice

When you port code from a new third-party project, add a
section here with:
1. Source URL
2. License (verbatim text)
3. Sprint spec reference
4. Port scope (which files were adapted, which were dropped)
5. Any modifications / deviations from the upstream

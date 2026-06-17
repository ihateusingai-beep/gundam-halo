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

## Add or update a notice

When you port code from a new third-party project, add a
section here with:
1. Source URL
2. License (verbatim text)
3. Sprint spec reference
4. Port scope (which files were adapted, which were dropped)
5. Any modifications / deviations from the upstream

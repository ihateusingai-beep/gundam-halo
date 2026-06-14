# Microphone Permission — Setup Guide

Gundam Halo uses your microphone for **hold-to-talk** and **push-to-talk**
voice input. The mic is **only active while you are pressing the mic
button in the cockpit** — the rest of the time nothing is recorded,
nothing is streamed, and the AudioContext is suspended.

If the cockpit shows **"Microphone permission denied"**, this guide
walks you through the three runtimes (Browser, Tauri, system-level)
and how to permanently grant mic access on each.

---

## TL;DR

| Runtime | Permanent grant path | What "permanent" means |
|---|---|---|
| **Chrome @ 127.0.0.1:5173** | Click "Allow" in the prompt; Chrome remembers it until you clear site data | Survives reload, restart, Chrome update |
| **Tauri desktop shell** | First launch shows the macOS dialog → click "Allow"; toggle under System Settings | Survives app restart, OS update |
| **Tailscale / remote browser** | Same as Chrome, but remote host may not be in the "Allow" list | Same as Chrome |

If you previously clicked **"Block"**, this guide shows how to
un-block (Chrome settings page or incognito window).

---

## 1. Chrome (browser dashboard)

The most common path during development: you open
<http://127.0.0.1:5173> in Chrome, click the mic button, and
Chrome shows a permission prompt at the top of the page.

### First-time grant

1. Click the **mic button** in the right panel (the 🎤 icon).
2. Chrome shows a small dialog at the top of the page:
   > `127.0.0.1:5173 wants to use your microphone`
3. Click **Allow**.
4. The mic button should turn from grey to accent color within 1-2 s.

After this, **Chrome remembers the decision for that origin** —
reloading the page, restarting Chrome, even rebooting Mac won't
ask again. The decision is stored in your local profile
(`~/Library/Application Support/Google/Chrome/...`) and only
gets cleared when you:

- Clear site data for `127.0.0.1` (Chrome DevTools → Application →
  Storage → "Clear site data")
- Uninstall Chrome
- Sign out of Chrome profile (sync'd permissions)

### If you previously clicked "Block"

Chrome memorises "Block" the same way. To reverse:

**Option A — Settings page:**

1. Open `chrome://settings/content/microphone` in a new tab
2. Scroll to **Customized behaviours**
3. Find `http://127.0.0.1:5173` (or any entry under
   `Not allowed to use your microphone`) and click the **trash
   icon** to remove it
4. Reload the dashboard; Chrome will ask again — click **Allow**

**Option B — Site info popup:**

1. With the dashboard open, click the **🔒 lock icon** (or **ⓘ
   info icon**) in the URL bar
2. Find **Microphone** in the dropdown
3. Change from **"Block (default)"** to **"Allow"**
4. Reload the page

**Option C — Incognito window:**

1. `Cmd+Shift+N` to open a new incognito window
2. Navigate to <http://127.0.0.1:5173>
3. Incognito windows have fresh permission state; click
   **Allow** when prompted

### Localhost caveat

Chrome has a **special policy for `127.0.0.1` / `localhost`** that
**always asks the first time** you visit a port, even if you've
set the default behaviour to "Sites can use your microphone
without asking". This is by design — it stops malicious local
apps from silently activating your mic. After the first Allow
click, subsequent reloads on the same origin don't re-prompt.

If you want to skip the prompt even for the first visit, you
need to launch Chrome with the `--unsafely-treat-insecure-origin-as-secure`
flag for the specific origin, but that's discouraged for a
real microphone permission (the prompt exists for a reason).

---

## 2. Tauri desktop shell (the Mac app)

When you launch the bundled Mac app (`Gundam Halo.app` from
`/Applications`, or via `npm run tauri dev` during development),
**macOS itself** handles the mic permission — not the browser
engine inside the WebView. The decision is stored under
**System Settings → Privacy & Security → Microphone** and
survives everything.

### First-time grant

1. Launch the app (double-click `Gundam Halo.app` or run
   `npm run tauri dev` from `frontend/`).
2. macOS shows a system dialog the first time the app tries
   to use the mic:
   > `"Gundam Halo" would like to access the microphone.`
3. Click **Allow**.

After this, **the app can use the mic without re-prompting**.
The toggle in System Settings is now **on**.

### Verifying / reversing the decision

1. Open **System Settings** → **Privacy & Security** → **Microphone**
2. Find **Gundam Halo** in the list
3. Toggle on/off as desired
4. Quit and re-launch the app to apply

### Required Info.plist entries

Tauri 2 reads macOS usage strings from
`frontend/src-tauri/tauri.conf.json` under
`bundle.macOS.infoPlist`. The relevant keys (already set in this
project) are:

| Key | Why |
|---|---|
| `NSMicrophoneUsageDescription` | Required by macOS for any app that wants mic access. Without it, the app is rejected at install/launch. |
| `NSSpeechRecognitionUsageDescription` | Required for offline Whisper ASR fallback. |
| `NSAccessibilityUsageDescription` | Required for the macOS accessibility tool (reads on-screen text on demand). |
| `NSAppleScriptEnabled` | Enables AppleScript automation (we ship tools for it). |

If you fork the project, double-check these are still set —
the App Store review process rejects apps that touch mic /
speech / accessibility without the corresponding string.

---

## 3. Tailscale / remote browser

If you access the dashboard over Tailscale from another device
(e.g. your iPad at `http://gundam-halo.tailnet.ts.net:5173`),
the mic permission is governed by **that device's browser** —
not the host's.

iPad / iPhone Safari will ask the first time; click Allow.
The decision is per-origin per-device, just like Chrome on a
single Mac.

If you're on Android Chrome, the same flow applies.

---

## 4. In-app signals — what the cockpit tells you

| State | What the cockpit shows | What to do |
|---|---|---|
| **Granted** | 🎤 button pulses accent color, "Hold to talk" hint | Use it |
| **Denied** | Red border on mic button, "Mic permission denied" hint, error text below | See section 1 or 2 above |
| **Unsupported** | Grey mic button, "Not supported" hint | Browser doesn't expose `getUserMedia` — try a different browser |
| **Error** | Red mic button, error text below | Hover for details, or check DevTools console |

The cockpit **does not** auto-retry the mic prompt after a
denial — the browser only re-prompts in response to a user
gesture (click). To recover from a denial, click the mic
button again; if the browser has blocked it permanently,
follow section 1 (Chrome) or 2 (Tauri) to unblock.

---

## 5. Privacy notes

- Gundam Halo's mic stream goes **PCM frames** to
  `ws://127.0.0.1:8000/ws/voice` (or the Tailscale equivalent)
  on the local backend.
- The backend runs **Whisper locally** for ASR (no cloud
  upload), then sends the transcribed text to the LLM provider
  (MiniMax by default).
- The mic stream is **never persisted to disk**. ASR
  transcription is in-memory only.
- The mic is **only active while you're holding the mic
  button**. Releasing the button runs VAD on the buffered
  audio, then ASR, then drops the raw audio.

For the full data-flow diagram, see
[`docs/ARCHITECTURE.md` §15 Voice + Live2D Interaction
Layer](../ARCHITECTURE.md).

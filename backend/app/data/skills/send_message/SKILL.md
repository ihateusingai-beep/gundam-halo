---
name: send_message
description: Send a message via WhatsApp / iMessage / Signal / SMS using YOLO-based UI detection (no official APIs).
user-invocable: true
---

# send_message

Send a text message via WhatsApp, iMessage, Signal, or SMS.
Uses pyautogui + YOLO computer vision (Sprint 30 Track A) to
detect the messaging app's UI elements. **There are no
official APIs for any of these platforms** — the tool drives
the GUI.

`enabled = false` by default (opt-in via
`~/.gundam-halo/config.toml [tools.send_message] enabled =
true`). The YOLO model needs to be downloaded once via
`scripts/download_yolo_model.py`.

## Operating Loop

1. **Confirm the recipient.** "Send 'hi' to Ken" — the
   tool needs an unambiguous contact name. If the user
   says "send to my sister", ask which platform / handle.
2. **Take a screenshot first.** The YOLO detector needs
   the target app open and visible. If the app is in the
   background, bring it forward with `open_app` first.
3. **Type slowly.** `typing_delay_s` (default 0.05s) —
   pyautogui's default is 0.0 (instant) which races the
   app. Don't lower it.

## Examples

```
send_message(platform="whatsapp", contact="Ken Cheng", message="On my way")
send_message(platform="imessage", contact="+852-9876-5432", message="hi")
send_message(platform="signal", contact="@ken.yue", message="got it")
send_message(platform="sms", contact="+1-555-0100", message="running late")
```

## Red Lines

- **NEVER auto-send without explicit confirmation.** The
  runtime sends a `send_message_blocked` event to the
  cockpit; the user must approve via the dashboard
  before the message goes out. Do not retry.
- Don't loop send_message calls. Each one opens a
  new message window. If the user says "send to 5
  contacts", make 5 separate calls with the user's
  approval for each.

## Recovery

- "YOLO model missing" → run `scripts/download_yolo_model.py`
  (~50 MB download). The runtime won't auto-download.
- "platform not supported" → `send_message` only supports
  whatsapp / imessage / signal / sms. For Telegram, use
  the bot (not this tool). For email, use AppleScript
  via `apple_script` with the Mail.app dictionary.
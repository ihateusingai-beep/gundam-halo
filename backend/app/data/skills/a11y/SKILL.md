---
name: a11y
description: Drive the Mac UI via the Accessibility API. Requires MacControlConfig.a11y_enabled=true and user grant of Accessibility permission to the host terminal app.
user-invocable: true
---

# a11y

Drive the Mac UI via the Accessibility API. Used for
window/menu traversal, button activation, text-field focus,
and getting the current keyboard focus. Lower-level than
`open_app` / `screenshot`; use this when the user wants
specific UI element interaction (not just "what's on screen").

## Operating Loop

1. **Check `MacControlConfig.a11y_enabled` is true.** If
   false, the tool refuses with a clear error pointing at
   the config flag. Don't try `osascript` as a workaround —
   the user has explicitly disabled a11y for a reason.
2. **Grant Accessibility permission to the host terminal
   app** (Tauri shell, or the `uvicorn` terminal). macOS
   prompts the first time; subsequent calls are silent.
   Without this grant, every a11y call returns "permission
   denied".
3. **Combine with `screenshot`** — the a11y tree gives you
   element references; the screenshot gives you visual
   context. For "click the blue button in the corner", you
   need both.

## Examples

```
a11y(action="frontmost_app")             → returns app name + window title
a11y(action="list_windows")             → returns [{app, title, role}]
a11y(action="find_element", role="button", title="Send")
a11y(action="click", ref="button-1")
a11y(action="set_focus", ref="text-field-3")
a11y(action="type_text", text="Hello")
```

## Red Lines

- Don't use a11y to interact with password fields. The
  runtime blocks this; if you genuinely need to fill a
  password, use the dedicated `password` flow (not
  exposed to the LLM in v0.1.5+).
- Don't loop a11y clicks blindly. Each call should be
  informed by a `screenshot` or `find_element` first.
  Blind retry loops burn CPU and pollute audit.log.

## Recovery

- "Accessibility permission denied" → tell the user to open
  System Settings → Privacy & Security → Accessibility and
  toggle on the host terminal app. Don't retry.
- "Element not found" → re-list windows or take a
  screenshot; the UI may have moved.
---
name: system_settings
description: Open a specific System Settings pane (Wi-Fi, Bluetooth, Display, etc.) by Apple URL scheme.
user-invocable: true
---

# system_settings

Open a System Settings pane directly via the
`x-apple.systempreferences://` URL scheme. Avoids the user
having to navigate manually.

## Operating Loop

1. **Use the canonical URL token.** The runtime ships a
   list of valid tokens (`com.apple.preference.network`,
   `com.apple.preference.displays`, etc.). If you pass an
   unknown token, the tool returns "preference pane not
   found" and you should ask the user for the path or use
   a fallback.
2. **For actions that require auth (e.g. Accessibility
   privacy), just opening the pane is the most you can do.**
   The user must click the toggle themselves; don't try to
   script past it.

## Examples

```
system_settings(pane="network")        → Wi-Fi
system_settings(pane="displays")
system_settings(pane="sound")
system_settings(pane="security")      → opens to General; user clicks Accessibility
system_settings(pane="bluetooth")
```

## Red Lines

- Don't pass `pane="<token with quotes>"` — the runtime
  escapes; if you need to bypass, file a bug, don't hack.
- Don't loop `system_settings(pane=...)` to navigate by
  brute force. Each call bounces through Spotlight; it
  takes ~1s. If you don't know the right token, ask.

## Recovery

- "preference pane not found" → ask the user which setting
  they want to change. Don't guess.
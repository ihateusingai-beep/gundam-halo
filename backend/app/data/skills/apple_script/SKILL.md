---
name: apple_script
description: Run an AppleScript snippet to drive Mac apps that have an OSA dictionary (Notes, Mail, Finder, Safari, etc.).
user-invocable: true
---

# apple_script

Run an AppleScript snippet via `osascript -e`. Use this for
apps that have an OSA dictionary (Notes, Mail, Finder, Safari,
Reminders, Calendar, Music, etc.) when you need scripted
interaction that `open_app` / `a11y` can't easily provide.

## Operating Loop

1. **Confirm `MacControlConfig.apple_script_enabled=true`.**
   Default is `true`. If the user disabled it, the tool
   refuses; respect the choice.
2. **Quote your strings carefully.** AppleScript string
   literals use `"..."` and embedded quotes need escaping.
   Pass the script as one multi-line string with
   backslash-continuations, or use single-quoted shell
   strings.
3. **Wrap long scripts in `on run` / `end run`** so the
   script is self-contained. AppleScript can leak globals
   across invocations.

## Examples

```
apple_script(script='tell application "Notes" to create note with text "Hello"')
apple_script(script='tell application "Finder" to set folder of front window to POSIX file "/Users/kencheng/workspace"')
apple_script(script='tell application "Safari" to do JavaScript "document.title" in current tab of front window')
```

## Red Lines

- Don't AppleScript `System Events` to type keystrokes
  into another app as a workaround for a missing a11y
  permission. Either get the a11y grant or don't do the
  automation. Looping keystroke injection burns audit.log.
- Don't `do shell script` from inside AppleScript — it
  bypasses the `shell_exec` allowlist. If you need shell
  work, call `shell_exec` directly so the policy check
  applies.

## Recovery

- "execution error: ..." (OSA error -1712 etc.) → AppleScript
  runtime error. Wrap with `try/on error` and surface the
  message. Don't retry without changing the script.
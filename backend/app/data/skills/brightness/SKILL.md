---
name: brightness
description: Set display brightness (0-100%) on the main or external display.
user-invocable: true
---

# brightness

Set display brightness via the `brightness` CLI
(https://github.com/nriley/brightness, bundled with Homebrew).

## Operating Loop

1. **0 = off, 100 = max.** The CLI takes a 0-1 float; this
   tool accepts 0-100 and converts.
2. **Display selection:** default is the built-in display.
   Pass `display=N` for external displays (0-indexed).
3. **Changes persist across reboots.** Don't surprise the
   user with a brightness change in the middle of a
   presentation; ask first.

## Examples

```
brightness(level=50)
brightness(level=80, display=1)
brightness(level=0)         → effectively off (still on; just dim)
```

## Red Lines

- The brightness CLI needs sudo on some macOS versions. If
  blocked, surface the password prompt to the user; don't
  cache credentials in the agent context.

## Recovery

- "sudo required" → the user needs to either pre-grant sudo
  NOPASSWD for `/usr/local/bin/brightness` or run the
  command manually. Don't retry.
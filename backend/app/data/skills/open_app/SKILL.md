---
name: open_app
description: Launch or focus a Mac application by name (e.g. "Safari", "Terminal", "Notes").
user-invocable: true
---

# open_app

Launch an app via `open -a <name>` or focus it if already
running. Bundled apps install in `/Applications` or
`/System/Applications`; user-installed apps in `~/Applications`.

## Operating Loop

1. **Prefer the canonical app name.** "Safari", not
   "safari.app" or "com.apple.Safari". The runtime resolves
   the bundle identifier internally.
2. **For deep links, pass `--args` or a URL.** `open -a
   Safari https://example.com` opens Safari and navigates
   to the URL. The tool accepts a `url` field that maps to
   this.
3. **For Terminal commands, use `shell_exec` instead.**
   `open_app` is for GUI apps; `shell_exec` is for CLI.

## Examples

```
open_app(name="Safari")
open_app(name="Notes")
open_app(name="Safari", url="https://github.com")
open_app(name="Terminal", args=["~/workspace/gundam-halo"])
```

## Red Lines

- Don't open apps that need a separate permission grant
  the user hasn't given (e.g. screen-recording apps,
  accessibility-using apps that haven't been approved).
  The runtime surfaces the permission error; don't retry.
- Don't `open_app(name="Finder", url="javascript:...")` or
  similar. The URL handler may execute arbitrary code in
  the app's context.

## Recovery

- "Unable to find application '<name>'" → check the name.
  Use `ls /Applications | grep -i <name>` to discover.
- "permission denied" → the app needs a TCC grant the
  user hasn't given. Tell them, don't retry.
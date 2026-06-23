---
name: notify
description: Show a macOS notification banner (Notification Center).
user-invocable: true
---

# notify

Show a macOS notification via `osascript -e 'display
notification ...'`. Useful for surfacing long-running task
completion, alerts, or gentle reminders without interrupting
the user's flow.

## Operating Loop

1. **Keep title ≤ 50 chars, body ≤ 200 chars.** The macOS
   Notification Center truncates aggressively past those
   bounds.
2. **Use sparingly.** A notification every minute is
   noise. Reserve for: task completion (>5s), errors the
   user needs to know about, scheduled reminders.
3. **For silent notifications, omit the `sound` field.**
   Default is `default` (system sound). Pass `sound=null`
   for a banner with no audio.

## Examples

```
notify(title="Sprint 36 done", body="Tier 1 + Tier 2 committed")
notify(title="VAD model missing", body="Download from menu bar → Settings", sound="Basso")
notify(title="Reminder", body="Standup in 10 min", sound=null)
```

## Red Lines

- macOS rate-limits notifications to ~5 per minute per app
  beyond which they're coalesced or dropped. Don't try to
  bypass by spawning multiple notification banners.
- Don't include API keys, tokens, or sensitive data in
  the title or body — notifications are visible on the
  Lock Screen by default.

## Recovery

- "Notifications are not allowed for this app" → the user
  must enable Notifications for the host terminal in
  System Settings → Notifications. Don't retry.
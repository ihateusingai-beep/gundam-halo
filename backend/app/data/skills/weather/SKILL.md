---
name: weather
description: Look up the current weather for a location. Uses the wttr.in service (no API key required).
user-invocable: true
---

# weather

Fetch current weather from wttr.in (no API key required, but
rate-limited and accuracy is city-level, not street-level).
For Hong Kong / Tokyo / etc., use the city name. For
specific coordinates, use `lat,lon`.

## Operating Loop

1. **Default location is the user's `USER.md` "timezone"
   field.** If `USER.md` says "Asia/Hong_Kong", the tool
   defaults to Hong Kong. Override with `location=<city>`.
2. **Output is prose.** wttr.in returns multi-line ASCII
   weather. Don't try to parse; show it to the user
   directly via TTS in voice mode.
3. **For forecasts >3 days, use a real API.** wttr.in is
   good for "is it raining now"; bad for "next Tuesday".

## Examples

```
weather()                                       → default location
weather(location="Tokyo")
weather(location="22.3,114.2")                  → HK by lat/lon
weather(format="short")                         → one-line summary
```

## Red Lines

- wttr.in is a free service; don't poll it. Once per
  turn is the max reasonable rate. For ambient
  temperature in the cockpit HUD, cache the value for
  10 minutes (not implemented in v0.1.5; manual cache
  for now).

## Recovery

- "rate limited" → back off and retry in 60s. Don't retry
  immediately.
---
name: flight_finder
description: Search for flights between two cities on a given date. Real aviationstack API (if api_key set) or URL-builder fallback.
user-invocable: true
---

# flight_finder

Search for flights between two airports on a given date.
Real aviationstack API (free tier 100 req/month, paid
$50/mo for 10k) when `tools.flight_finder.api_key` is set;
otherwise falls back to a Google Flights URL builder.

## Operating Loop

1. **Confirm the date format.** `YYYY-MM-DD` only. Don't
   try to parse "next Tuesday" — convert to a date first
   (use the user's locale + timezone from `USER.md`).
2. **For round trips, call twice** (once for outbound,
   once for return). The tool doesn't bundle them.
3. **For "cheapest this month",** make 4-5 calls with
   different dates and pick the lowest. Don't try to be
   clever with `aviationstack`'s date-range endpoint —
   the free tier doesn't support it.

## Examples

```
flight_finder(origin="HKG", destination="NRT", date="2026-07-15")
flight_finder(origin="HKG", destination="LHR", date="2026-09-01", top_n=10)
flight_finder(origin="HKG", destination="TPE", date="2026-08-10", cabin="business")
```

## Red Lines

- **Don't blindly trust the price.** Aviationstack returns
  cached / delayed prices; for actual booking, the user
  must visit the airline's site (use the URL the tool
  returns). Tell the user "this is a reference price; book
  through the official site".
- **Don't loop `flight_finder` more than 10x in a turn.**
  Each call burns aviationstack quota. For "find me the
  cheapest day next month", sample 5 dates max.

## Recovery

- "401 / 403" from aviationstack → API key invalid or
  rate-limited. The tool falls back to URL builder; tell
  the user "the URL builder doesn't show prices — here's
  a Google Flights link instead".
- "no flights" → no scheduled service on that date.
  Try the adjacent dates.
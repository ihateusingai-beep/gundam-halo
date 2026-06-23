---
name: spotlight
description: Run a Spotlight (mdfind) search across the user's Mac. Returns file paths matching the query.
user-invocable: true
---

# spotlight

Run `mdfind` against the user's Spotlight index. Useful for
"find the PDF I downloaded last week" type queries.

## Operating Loop

1. **Use Spotlight syntax, not regex.** `mdfind "kind:pdf
   date:this week"` is the right shape. `mdfind` accepts
   the same query syntax as the Spotlight UI.
2. **Limit scope if you can.** `mdfind -onlyin ~/Downloads
   "<query>"` searches only Downloads — much faster than
   whole-system.
3. **For 0 results, broaden.** If a specific query returns
   nothing, drop the kind/date filter and search the whole
   filesystem.

## Examples

```
spotlight(query="kind:pdf date:this week")
spotlight(query="name:gundam-halo", onlyin="~/workspace")
spotlight(query="kind:image date:yesterday author:Ken")
```

## Red Lines

- Spotlight indexes the user's entire filesystem (including
  email, messages, downloads). **Don't dump the raw result
  list to a Telegram channel** without filtering for
  sensitive content first. The runtime returns paths;
  what's IN those files is private.

## Recovery

- "0 results" → broaden the query (drop filters, expand
  date range). Don't retry the same query.
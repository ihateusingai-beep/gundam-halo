# Gundam Halo — Backend

FastAPI server + MiniMax LLM provider + Mac control pane + channel adapters.

**Status**: 🚧 Scaffold (Day 1). Architecture spec: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Dashboard spec: [`../docs/DASHBOARD.md`](../docs/DASHBOARD.md).

## Quick start

```bash
# Install
uv sync
cp .env.example .env
# Edit .env — set MINIMAX_API_KEY at minimum

# Run
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8765

# Test
curl http://localhost:8765/health
# → {"status": "ok", "version": "0.1.0"}
```

## Module layout

```
app/
├── main.py              # FastAPI entry
├── core/                # registry, events, types, config, logging
├── engines/             # MiniMax provider
├── agents/              # simple, native_react, orchestrator
├── projects/            # per-project workspace
├── channels/            # telegram, signal
├── mac/                 # file_ops, shell, apple_script, etc. (policy-gated)
├── security/            # auth, audit
├── api/                 # REST routes
└── bridge/              # Mavis sub-agent bridge
```

## Architecture decisions

See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Key points:

- **Per-project isolation** (the key fix for Hermes messiness)
- **MiniMax API** as the only LLM backend (OpenAI-compatible)
- **Tailscale-only network** (no public internet)
- **Default-deny Mac control** (path policy + command allowlist + audit log + confirmation)
- **Forked from OpenJarvis's core** (registry + event bus + types)

## What's working in this scaffold

- ✅ FastAPI app with `/health` endpoint
- ✅ Core registry + event bus + types
- ✅ Config loading (TOML + env vars)
- ✅ Structured logging
- ✅ MiniMax engine stub (scaffold only, real LLM call TBD)
- ✅ Basic audit log writer
- ✅ Basic Mac control policy + file_ops

## What's NOT working yet

- ❌ Real MiniMax API calls (need API key + tests)
- ❌ Telegram bot (no token yet, but scaffolding ready)
- ❌ AppleScript / Accessibility API (mac-specific)
- ❌ Session manager (skeleton only)
- ❌ Project workspace CRUD (skeleton only)
- ❌ Mavis bridge (TBD)
- ❌ Tailscale auth enforcement (TBD)
- ❌ Full test coverage

## Development

```bash
# Install dev deps
uv sync --extra dev

# Run tests
uv run pytest

# Lint
uv run ruff check app/ tests/

# Auto-fix
uv run ruff check --fix app/ tests/
```

## License

MIT — see [`../LICENSE`](../LICENSE).

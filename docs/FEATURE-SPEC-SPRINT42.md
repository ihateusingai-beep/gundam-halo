# Sprint 42 — Backend security hardening + ops polish

**Date**: 2026-06-25
**Status**: Draft
**Author**: Mavis
**Priority**: Medium (closes 2 latent security/UX gaps + adds missing Tailscale ACL docs)

## Goal

Close three open items from the Sprint 37-38 function-review audit:

1. **Bug 2 (UX)**: `GET /api/health` returns 404 (the router is mounted at `/health`, not `/api/health`). Some external health checks (Tailscale ACL probes, launchd KeepAlive) expect `/api/health`. Add an alias so both work.
2. **TOML fail-loud (security)**: `app/core/config_loader.py:_load_toml` calls `tomllib.load(f)` with no try/except. A malformed `~/.gundam-halo/config.toml` raises an unhandled `tomllib.TOMLDecodeError` at backend startup → backend crashes with a stack trace. Wrap the load + report a friendly error pointing at the offending file + line + column.
3. **Tailscale ACL docs (operational)**: Profile memory + multiple tickets (M10-C, M11, M13) reference Tailscale, but there's no single operational doc. Consolidate into `docs/SECURITY-HARDENING.md` with the install.sh `--with-tailscale` hints + an explicit ACL JSON snippet the user can paste into their Tailscale admin console.

The original Sprint 42 brainstorm also included:
- **file_write_paths tightening** — already tight (`~/workspace` + `~/.gundam-halo/projects`, not `~/`). No change needed; **verified during investigation**.
- **ChannelRegistry cold-start fix** — already fixed in Sprint 32 P0-1 v2 (eager import in `app/channels/__init__.py`). Verified `GET /api/channels` returns 200 on a fresh HALO_HOME.

## Why now

Sprint 37/38 ship the voice cold-start + held-out eval plumbing, but the audit function review (2026-06-24) surfaced these gaps. Cheap to fix (no new features, just polish + docs). Closes user-visible issues before Sprint 39 (Frontend dashboard polish) lands.

## Design

### 1. Bug 2 fix — `/api/health` alias

The `health.router` (defined in `app/api/health.py`) is mounted at `prefix="/health"`. The frontend uses `/health` (no prefix) which works. External health checks (Tailscale probes, launchd KeepAlive `SuccessfulExit=false` predicates) often expect `/api/health` (REST convention).

**Fix**: Change the mount to `prefix="/api/health"` so the route serves at `/api/health`. The current `/health` mount is preserved as an **alias** route in `app/api/health.py`:

```python
# app/api/health.py
@router.get("", response_model=HealthResponse)  # existing — serves /api/health
async def health() -> HealthResponse: ...

@router.get("/legacy", response_model=HealthResponse, include_in_schema=False)
async def health_legacy() -> HealthResponse:
    """Alias for /health — kept for backwards compat with any
    smoke scripts that still call the bare path."""
    return await health()
```

Mount:
```python
halo_app.include_router(health.router, prefix="/api/health", tags=["health"])
halo_app.include_router(health_legacy_alias_router, prefix="/health", tags=["health-legacy"])
```

(Simpler than dual-mounting: just keep the bare-`/health` route as a separate `/health` router. Cleaner than adding a route-level alias inside `health.py`.)

### 2. TOML fail-loud

`app/core/config_loader.py:_load_toml` calls `tomllib.load(f)` with no error handling. Sprint 42 wraps the call + adds a friendly error:

```python
def _load_toml(path: Path) -> dict:
    """Load a TOML file. Returns empty dict if not found.

    Raises ConfigParseError with the offending line/column
    on malformed input (per Sprint 42 hardening). The
    backend's `lifespan` catches this and surfaces a
    friendly message instead of a stack trace.
    """
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigParseError(
            config_path=path,
            line=e.lineno,
            column=e.colno,
            message=str(e),
        ) from e
```

`ConfigParseError` is a new exception in `app/core/config_loader.py`:

```python
class ConfigParseError(RuntimeError):
    """Raised when ~/.gundam-halo/config.toml is malformed.

    The lifespan handler in app/main.py catches this and
    prints a 1-line error message pointing at the file +
    line + column, then exits with code 2 (config error).
    Without this, the backend crashes with a raw
    tomllib stack trace that's hard to read on cold start.
    """
    def __init__(self, config_path: Path, line: int, column: int, message: str):
        self.config_path = config_path
        self.line = line
        self.column = column
        super().__init__(
            f"Failed to parse {config_path}:{line}:{column} — {message}. "
            f"Fix the TOML syntax or run `uv run python -c \"import tomllib; tomllib.load(open('~/.gundam-halo/config.toml', 'rb'))\"` "
            f"to see the parse error yourself."
        )
```

`app/main.py:lifespan` catches `ConfigParseError` + logs a friendly message + re-raises (so the backend exits non-zero — process supervisor notices).

### 3. Tailscale ACL docs

New `docs/SECURITY-HARDENING.md` (~200 LoC) covering:

- **Why Tailscale (not public internet)**: per profile memory — "NO public internet exposure".
- **install.sh `--with-tailscale` flag**: prints the ACL snippet below.
- **ACL JSON snippet** (paste into Tailscale admin → Access Controls):
  ```json
  {
    "acls": [
      {"action": "accept", "src": ["tag:admin"], "dst": ["tag:gundam-halo:8765"]},
      {"action": "accept", "src": ["tag:gundam-halo"], "dst": ["tag:gundam-halo:8765"]}
    ],
    "tagOwners": {
      "tag:admin": ["autogroup:admin"],
      "tag:gundam-halo": ["tag:gundam-halo"]
    },
    "autoApprovers": {
      "routes": {"tag:gundam-halo": ["tag:admin"]}
    }
  }
  ```
- **`tailscale up` device tags** the user runs on the Mac:
  `sudo tailscale up --advertise-tags=tag:gundam-halo --hostname=gundam-halo`.
- **Health check ACL probe** the user can add (Tailscale's `healthCheck` field):
  `{"type": "http", "port": 8765, "path": "/api/health", "expectedStatus": 200}`.
- **Common pitfalls**:
  - MagicDNS hostname must match `server.tailscale_hostname` in config.toml (default: `gundam-halo`).
  - The Mac's Tailscale node must be tagged `tag:gundam-halo` or the ACL won't apply.
  - The backend refuses non-Tailscale connections when `server.require_tailscale = true` (the default).
- **Audit log location + rotation**: `~/.gundam-halo/logs/audit.log` (rotated by `app/core/security.py:rotate_audit_log`).

Cross-link from existing `config.toml.example` `[server]` block + `install.sh` `--with-tailscale` branch.

## Test changes

- `tests/api/test_health_route.py` NEW — 4 tests (route present at both paths, returns 200, version matches `__version__`, name == "gundam-halo").
- `tests/core/test_config_loader_toml_errors.py` NEW — 3 tests:
  - `test_malformed_toml_raises_config_parse_error` (e.g. unclosed `[[section`).
  - `test_config_parse_error_carries_path_line_column` (asserts the error attributes).
  - `test_missing_toml_returns_empty_dict` (regression — ensure we don't break the existing happy path).
- `tests/security/test_tailscale_acl_doc.py` NEW — 2 tests (validates the JSON snippet in SECURITY-HARDENING.md parses cleanly + the doc references the install.sh flag).

## Files to create / modify

- `backend/app/api/health.py` (modify — add `/legacy` alias route)
- `backend/app/main.py` (modify — change mount prefix + add legacy alias router; catch `ConfigParseError` in lifespan)
- `backend/app/core/config_loader.py` (modify — add `ConfigParseError`, wrap `_load_toml`)
- `docs/SECURITY-HARDENING.md` NEW (~200 LoC)
- `docs/SECURITY-HARDENING.md` (cross-link from `config.toml.example [server]` block + `install.sh --with-tailscale` branch)
- `tests/api/test_health_route.py` NEW (~50 LoC, 4 tests)
- `tests/core/test_config_loader_toml_errors.py` NEW (~80 LoC, 3 tests)
- `tests/security/test_tailscale_acl_doc.py` NEW (~50 LoC, 2 tests)
- `docs/CHANGELOG.md` (entry)
- `docs/FEATURE-SPEC-SPRINT42.md` (this file)

Total: ~500-600 LoC across ~9 files.

## Acceptance criterion

- `GET /api/health` returns `200 {"status": "ok", "version": "0.1.12", ...}` on a fresh HALO_HOME.
- `GET /health` continues to return the same payload (alias route).
- A config.toml with `[[voice.vad]\n  bad = ` (unclosed bracket) produces a one-line error on startup:
  ```
  ERROR Failed to parse /Users/kencheng/.gundam-halo/config.toml:5:3 — ...
  ```
  instead of a raw `tomllib.TOMLDecodeError` stack trace.
- `docs/SECURITY-HARDENING.md` exists with the ACL JSON snippet + install.sh cross-link.
- Full backend pytest stays green; no frontend changes.

## Out of scope (deferred to future sprints)

- Auto-rotate audit log file (currently rotated manually if the size cap is hit — `app/core/security.py:rotate_audit_log` is a TODO).
- Tailscale `Funnel` / `Serve` integration (exposing the backend to the public internet with auth — explicitly disallowed by profile memory).
- Restrict `[server].host` default from `0.0.0.0` to `127.0.0.1` (currently the install.sh `--with-tailscale` path relies on `0.0.0.0` + Tailscale for routing; changing the default would break that flow).
- Process-level sandboxing (Seatbelt on macOS, AppArmor on Linux) — separate Sprint.

## Version bump

`__version__` 0.1.11 → **0.1.12** (PATCH bump per Mavis memory rule —
security fix is correctness, not a user-facing feature change, but
the version surface consistency matters for the audit trail).
Frontend versions unchanged (0.1.7 from Sprint 33b).

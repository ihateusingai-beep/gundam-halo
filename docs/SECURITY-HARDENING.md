# Gundam Halo — Security Hardening Guide

**Sprint 42** — consolidates Tailscale ACL setup + audit log
rotation + security defaults into a single operational
document. Cross-linked from `config.toml.example [server]`
block + `install.sh --with-tailscale` branch.

## Why Tailscale (not public internet)

Per `~/.mavis/agents/mavis/memory/MEMORY.md` (2026-06-04):

> Gundam Halo control surface priority — Gundam Halo is
> single-user on Mac, primary control surface is the Tauri
> app + web dashboard (Tailscale). Telegram was architected
> as a phone fallback but the user does not actively use it
> in 2026-06. Don't lead with Telegram features.

The backend refuses non-Tailscale connections by default
(`server.require_tailscale = true`). Exposing the backend
to the public internet is explicitly disallowed.

## Tailscale ACL — paste into your Tailscale admin console

Go to [Tailscale admin → Access Controls](https://login.tailscale.com/admin/acls/file)
and replace the ACL JSON with the snippet below (merge with
your existing ACLs if you have other devices on your tailnet):

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["tag:admin"],
      "dst": ["tag:gundam-halo:8765"]
    },
    {
      "action": "accept",
      "src": ["tag:gundam-halo"],
      "dst": ["tag:gundam-halo:8765"]
    },
    {
      "action": "accept",
      "src": ["tag:gundam-halo"],
      "dst": ["tag:gundam-halo:80,443,8080,9090"]
    }
  ],
  "tagOwners": {
    "tag:admin": ["autogroup:admin"],
    "tag:gundam-halo": ["tag:gundam-halo"]
  },
  "autoApprovers": {
    "routes": {"tag:gundam-halo": ["tag:admin"]}
  },
  "healthCheck": {
    "enabled": true,
    "type": "http",
    "port": 8765,
    "path": "/api/health",
    "expectedStatus": 200
  }
}
```

### What each rule does

| Rule | Effect |
|---|---|
| `tag:admin → tag:gundam-halo:8765` | Lets your admin-typed devices (laptop, phone) reach the backend on port 8765 |
| `tag:gundam-halo → tag:gundam-halo:8765` | Loopback — lets the Mac reach itself over Tailscale (useful for `curl https://gundam-halo:8765/api/health` from your iPhone) |
| `tag:gundam-halo → tag:gundam-halo:80,443,8080,9090` | Lets the backend reach local services (Live2D model server, mlx-whisper daemon, etc.) — adjust to your stack |
| `tagOwners.tag:admin = autogroup:admin` | Standard Tailscale convention — `autogroup:admin` is automatically populated |
| `tagOwners.tag:gundam-halo = tag:gundam-halo` | Lets the Mac self-tag itself (needed for `tailscale up --advertise-tags=tag:gundam-halo`) |
| `autoApprovers.routes.tag:gundam-halo` | Auto-approves subnet routes advertised by `tag:gundam-halo` devices (skip the manual approval in Tailscale admin) |
| `healthCheck` | Tailscale pings `/api/health` every 60 s; if 200 OK the node shows as healthy, otherwise as "needs login" / unreachable. **Requires Sprint 42's `/api/health` mount fix** (the bare `/health` mount from Sprint 32 was missing the `api/` prefix). |

## Advertise tags on the Mac

After applying the ACL above, run on the Mac:

```bash
sudo tailscale up \
  --advertise-tags=tag:gundam-halo \
  --hostname=gundam-halo
```

`--hostname=gundam-halo` sets the MagicDNS name — must match
`server.tailscale_hostname` in your `~/.gundam-halo/config.toml`
(default: `gundam-halo`). `--advertise-tags=tag:gundam-halo`
triggers Tailscale admin to ask you to approve the tag (one-time,
in the Tailscale admin UI under "Machines").

Verify:

```bash
tailscale status
# Look for `gundam-halo` in the output with tag `tag:gundam-halo`.

tailscale ping gundam-halo
# Should respond in <100 ms over the Tailscale DERP relay or
# direct WireGuard tunnel.

curl -s https://gundam-halo:8765/api/health
# Should return {"status": "ok", "version": "0.1.12", ...}
```

## Common pitfalls

1. **MagicDNS mismatch**: If `server.tailscale_hostname` in
   config.toml is `gundam-halo` but `tailscale up --hostname`
   sets it to `gundam-halos-mac`, the URL `https://gundam-halo:8765/api/health`
   404s. Fix: re-run `tailscale up --hostname=gundam-halo` (one
   command, no reinstall).
2. **Tag not approved**: `tailscale up --advertise-tags` requires
   admin approval in Tailscale admin → Machines. Until approved,
   the ACL won't apply. Fix: approve in the admin UI (you have
   24 hours after the request before the tag expires).
3. **`require_tailscale = false` accidentally set**: The
   backend then accepts connections from any source — anyone
   who can reach port 8765 can call `/api/mac/shell`. Audit
   check: `grep require_tailscale ~/.gundam-halo/config.toml` —
   should be `true` (the default).
4. **Tailscale DERP fallback latency**: First-time connections
   from a new device may go through the DERP relay (US/EU) for
   ~500 ms. Direct WireGuard kicks in after 3 successful
   handshakes; `tailscale status` shows `direct` vs `relay`.

## Audit log

The backend writes every mac-control operation (file_read /
file_write / shell / apple_script / notify / spotlight /
a11y) to:

```
~/.gundam-halo/logs/audit.log
```

Default rotation: **100 MB** (configurable via
`[security].audit_max_size_mb` in config.toml). When the log
hits the cap, `app/core/security.py:rotate_audit_log` (Sprint 34)
rotates it to `audit.log.1` and starts fresh.

Manual rotation (if you need to clear the log without filling
100 MB):

```bash
cd ~/.gundam-halo/logs && \
  mv audit.log audit.log.$(date +%Y%m%dT%H%M%SZ) && \
  : > audit.log
```

The backend's audit handler (`app/core/logging.py:audit_handler`)
reopens the file automatically when it rotates.

## Process-level hardening (manual, not auto-installed)

The install.sh script doesn't set up process-level sandboxing
(Sprint 42 is just docs + Bug 2 + TOML errors). For production
deployment, consider:

- **macOS Seatbelt profile** — restrict the backend process's
  file access to `~/.gundam-halo/` + `~/workspace/`. The
  backend's own `file_write_paths` policy is defence-in-depth,
  not a sandbox.
- **Linux AppArmor / SELinux profile** — same idea, kernel-
  enforced.

## Endpoints currently unprotected (Sprint 43)

Sprint 43 ships `POST /api/system/clear-crash-log` as part of the
self-healing backend. This endpoint is **currently unprotected**
(no auth layer) per the project's single-user assumption that all
`/api/system/*` routes are local-only. The action is benign
(wipes `~/.gundam-halo/state/crash_log.jsonl`; returns the
cleared event count), so the blast radius is low.

**Sprint 45 will add an auth layer** for all `/api/system/*`
endpoints. The mechanism is undecided — likely a shared-secret
token in `~/.gundam-halo/.env` (chmod 600) sent via the
`Authorization: Bearer <token>` header, since the cockpit is
already the only legitimate client. Tracked under the M12
hardening backlog.

Until then, **bind the backend to localhost** (the default —
`server.bind_address = "127.0.0.1"` in `config.toml.example`)
and rely on Tailscale for any remote access. Do not expose port
8765 to the public internet; per the project memory rule "NO
public internet exposure", the backend is **Tailscale-only**.

## Sprint 48 — Auth layer (belt + braces)

Sprint 48 closes the "Sprint 45 will add auth" note. Two checks
protect every privileged endpoint:

1. **Bearer token** (`Authorization: Bearer <token>`) — hard
   requirement, fail-closed. Stored in `~/.gundam-halo/.env`
   (mode 600) as `HALO_API_TOKEN`.
2. **Tailscale identity** (`Tailscale-Identity` header) —
   defence-in-depth, optional enhance. Enforced when
   `tailscaled` is reachable; skipped (with WARNING) when not.

### Threat model

| Threat | Bearer alone | Tailscale alone | Both |
|---|---|---|---|
| Random Tailscale peer on the tailnet | ✅ rejected | ❌ passes | **✅ rejected** |
| Leaked token used from non-Tailscale device | ❌ passes | ✅ rejected | **✅ rejected** |
| Localhost curl with leaked token | ❌ passes | ✅ rejected | **✅ rejected** |
| Both leaked to a fully-trusted Tailscale peer | — | — | ❌ passes (residual; mitigated by rotation) |

### Protected endpoints (16 total)

| Endpoint | Why protected |
|---|---|
| `POST /api/system/clear-crash-log` | wipes watchdog history |
| `POST /api/system/cancel-restart` | aborts self-restart |
| `GET /api/system/health-detailed` | reads crash log |
| `POST /voice/run-finetune` | spawns 30-60 min LoRA |
| `POST /voice/run-held-out-eval` | spawns eval job |
| `POST /api/setup/*` (11 endpoints) | writes config.toml |

Read-side stays open: `/voice/config`, `/voice/status`,
`/voice/eval-results`, `/voice/eval-corpus-breakdown`,
`/voice/list-jobs`, `/voice/self-record-corpora`,
`/api/system/gauges`, `/api/system/info`, `/api/health`,
`/api/setup/state`. Tailscale-locality + `127.0.0.1` binding
provides practical security for the read side.

### Bootstrap + rotation

```bash
# First-time setup — creates ~/.gundam-halo/.env with a fresh
# 32-byte URL-safe base64 token (mode 600).
./scripts/generate-auth-token.sh

# Rotation — replaces the existing token. The backend rejects
# the old token immediately on restart.
./scripts/rotate-auth-token.sh
```

Both scripts honour `$HALO_HOME`, preserve other env vars,
defensive `chmod 600` after edit, and print the new token
ONE TIME.

### Tauri integration

`frontend/src-tauri/src/auth.rs` reads `~/.gundam-halo/.env`
at startup and injects the token into the webview via an init
script (`window.__haloApiToken = "<token>"`). The frontend's
`lib/api.ts::authedRequest()` wrapper reads this global on
every fetch and adds `Authorization: Bearer <token>`.

The watchdog's curl helpers (`watchdog::curl_with_bearer`) do
the same for the Tauri IPC commands that shell out to the
backend (`get_backend_health`, `clear_crash_log`,
`cancel_restart`).

### Tailscale identity check

When `tailscaled` is reachable (local API on
`localhost:41112` macOS / unix socket Linux), the auth
dependency reads `Tailscale-Identity` (JWT), decodes the
payload, and enforces `[security.auth].tailscale_allowed_tags`
(empty = no filter). Unreachable tailscaled = skip with WARNING
(bearer-only mode for dev).

### Audit log

`~/.gundam-halo/logs/audit.log` (JSONL, 1 MB rotation):
```json
{"ts": 1782732509.123, "event": "auth_failure", "reason":
 "missing-bearer", "method": "POST", "path":
 "/api/system/clear-crash-log", "src_ip": "100.100.100.42"}
```
Implements the Sprint 13 TODO.

  enforced.
- **`HALO_REQUIRE_TAILSCALE=true`** env var — equivalent to
  setting `server.require_tailscale = true` in config.toml;
  useful for container deployments where the TOML mount
  isn't read until after the listener binds.

## See also

- `docs/ARCHITECTURE.md` §15 — voice layer security
- `docs/tickets/M10-C.md` — Tailscale setup ticket
- `docs/tickets/M11.md` — secret rotation policy
- `docs/tickets/M13.md` — production deployment checklist
- `~/.mavis/agents/mavis/memory/MEMORY.md` — Gundam Halo
  control-surface priority + Tailscale-only access pattern

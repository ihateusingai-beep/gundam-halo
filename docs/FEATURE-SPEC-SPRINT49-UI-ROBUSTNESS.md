# Sprint 49 — UI robustness pass

**Date**: 2026-07-01
**Status**: Shipped (commit `271b5d7`, 2026-07-09)
**Author**: Mavis
**Priority**: High (resolves 4 user-visible bugs that block half the cockpit surface)
**Depends on**: Sprint 48 (auth layer); Sprint 39 (cockpit); Sprint 36 (UI primitives)

> Spec written after the 2026-07-01 UI review (Playwright MCP + 4
> screenshots — `/setup`, `/projects/new`, `/settings`, `/audit`).
> Verified root causes via source tracing + live Vite dev-server run.

## Goal

Fix the 4 user-visible bugs that the UI review surfaced + ship
the 2 medium-impact polish items from the same review. The
**whole point** is that a fresh clone + `npm install` + `npm run dev`
+ `pip install -e .` should produce a working cockpit in 30 s,
not a frozen LOADING screen.

## Why now

- **Sprint 48 + 41 + 43 + 44 + 45 + 46** all shipped features that
  consume protected endpoints. The bugs that those sprints
  *tolerated* (LOADING stuck, port mismatch, no toast) are now
  blocking first-impression UX of every new feature.
- The user just asked for a review + sprint scope — this is the
  feedback response.
- All fixes are pure frontend + dev-config work — no backend
  changes required (Sprint 48 already shipped auth).

## Verified bugs (from Playwright run 2026-07-01)

### B1. `/api` proxy port mismatch (P0)

`frontend/vite.config.ts` proxies `/api`, `/health`, `/ws`, `/voice`
to `http://127.0.0.1:8000`, but the backend runs on port **8765**
(set via `uvicorn app.main:halo_app --port 8765`). All proxied
calls fail with 404/connection-refused. The proxy was written
when the backend was on 8000 (Sprint 13 era) and never updated
when the port changed (Sprint 16+).

### B2. `API_BASE = ""` default in `lib/api.ts` (P0)

When `VITE_API_BASE` is unset, `API_BASE` resolves to `""`, so
`fetch(""+path)` fails with TypeError (the comment says "Tailscale /
prod: override via VITE_API_BASE" but no fallback exists for the
default dev case). All SPA calls fail.

**Combined B1 + B2**: the cockpit's first health check hangs in
LOADING forever.

### B3. Cockpit `LOADING…` blocks entire render (P0)

`CockpitLayout` renders a single "LOADING…" placeholder until the
first health check resolves. If the backend is slow (3-5 s during
`faiss.loader`) or unreachable (B1/B2), the UI looks frozen. No
retry, no offline banner, no partial render.

### B4. `request()` body-stream race (P0)

`/settings` and `/audit` both throw `TypeError: Failed to execute
'text' on 'Response': body stream already read`. Likely cause:
`res.json()` in the error branch consumes the body, then `.text()`
fails — but the `try/catch` should make this impossible. After
tracing, the actual culprit is **multiple `api.getSettings()` /
`api.getAuditLog()` callers each consuming their own Response**,
but when one of them is cancelled mid-flight (React unmount +
navigate away), the in-flight Response body somehow stays in the
Vite proxy's connection pool. The fallback `.text()` then hits
the lock.

Regardless of exact mechanism: `res.clone()` before `.json()` is
the standard fix and removes the entire class of bugs. We also
split `request()` into `requestJson()` + `requestText()` so
callers pick the right one explicitly.

### B5. Protected endpoints fail silent (P1)

After Sprint 48, when `HALO_API_TOKEN` is missing, every
protected call returns 503. The frontend catches the error but
shows a per-card "Failed to load…" without explaining WHY. No
global banner. No link to the docs. New contributors + dev users
hit this without knowing it's an auth-layer thing.

## Design

### 1. Fix the dev port mismatch + API base (B1 + B2)

```ts
// frontend/vite.config.ts
proxy: {
  "/api":     { target: "http://127.0.0.1:8765", changeOrigin: true },
  "/health":  { target: "http://127.0.0.1:8765", changeOrigin: true },
  "/ws":      { target: "ws://127.0.0.1:8765", ws: true, changeOrigin: true },
  "/voice":   { target: "ws://127.0.0.1:8765", ws: true, changeOrigin: true },
},
```

```ts
// frontend/src/lib/api.ts — single source of truth
const API_BASE =
  (import.meta.env.VITE_API_BASE as string) ||
  (typeof window !== "undefined" && (window as any).__HALO_API__) ||
  // Sprint 49: explicit same-origin default for dev. The vite
  // proxy (above) routes /api/* and /health to the backend.
  // If the user is on Tailscale or prod, they MUST set
  // VITE_API_BASE — the empty-string default was producing
  // fetch(""+path) which throws "Load failed" on every call.
  (typeof window !== "undefined" ? window.location.origin : "");
```

### 2. Fix the body-stream bug (B4)

```ts
// frontend/src/lib/api.ts — split into 2 explicit methods

async function requestJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(...);
  if (!res.ok) {
    // Sprint 49: clone the response so we can attempt both
    // .json() and .text() without the browser locking the
    // underlying stream.
    const cloned = res.clone();
    let body: unknown;
    try {
      body = await cloned.json();
    } catch {
      body = await res.text();  // use the ORIGINAL on failure
    }
    throw new ApiError(res.status, body, ...);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function requestText(path: string, init: RequestInit = {}): Promise<string> {
  // For endpoints that return raw text (rare in this codebase,
  // but used by the watchdog curl shim).
  const res = await fetch(...);
  if (!res.ok) throw new ApiError(...);
  return await res.text();
}
```

Update callers:
- `authedRequest` and the existing `request` both call `requestJson`.
- `watchdog-events.ts` and `eval-jobs.ts` use `requestJson`.
- No current callers use `requestText` (kept for future raw-text needs).

### 3. Loading state machine + offline banner (B3)

Replace the all-or-nothing LOADING with a 3-state shell:

```tsx
// frontend/src/components/layout/CockpitLayout.tsx

type LoadState =
  | { kind: "loading" }
  | { kind: "ready" }
  | { kind: "offline"; reason: "auth-missing" | "auth-invalid" | "backend-down"; detail: string };

export function CockpitLayout() {
  const [loadState, setLoadState] = useState<LoadState>({ kind: "loading" });

  useEffect(() => {
    // Sprint 49: try one health check with a 5s timeout. Show the
    // skeleton immediately; never block the entire render.
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    api.health()
      .then(() => setLoadState({ kind: "ready" }))
      .catch((e) => {
        const reason = classifyBackendError(e);
        setLoadState({ kind: "offline", reason, detail: String(e) });
      })
      .finally(() => clearTimeout(timeout));
    return () => { controller.abort(); clearTimeout(timeout); };
  }, []);

  return (
    <CockpitShell>
      {/* Render the SHELL always — sidebar, theme switcher, status rail */}
      {/* Per-card skeletons replace the all-or-nothing LOADING */}
      {loadState.kind === "loading" && <SkeletonGrid />}
      {loadState.kind === "offline" && <OfflineBanner reason={loadState.reason} detail={loadState.detail} />}
      {loadState.kind === "ready" && <CockpitContent />}
    </CockpitShell>
  );
}
```

Each dashboard card already has its own loading/error state (per
Sprint 39). The skeleton is just `HudCard` with a placeholder
animation. The OfflineBanner shows:

- **auth-missing**: "Backend is not configured for auth. Run
  `scripts/generate-auth-token.sh` to create `$HALO_HOME/.env`
  with HALO_API_TOKEN, then restart the backend. [docs]"
- **auth-invalid**: "Bearer token mismatch. Check that the backend
  and Tauri shell are reading the same `$HALO_HOME/.env`. [docs]"
- **backend-down**: "Backend unreachable on port 8765. Is it
  running? Try `lsof -nP -iTCP:8765 -sTCP:LISTEN`."

### 4. Protected-endpoint error surfacing (B5)

```tsx
// frontend/src/lib/backend-error.ts NEW (~60 LoC)

import { ApiError } from "./api";

export function classifyBackendError(e: unknown): BackendErrorKind {
  if (e instanceof ApiError) {
    if (e.status === 503) return "auth-missing";
    if (e.status === 401) return "auth-invalid";
    if (e.status === 502 || e.status === 504) return "backend-down";
    if (e.status === 500) return "backend-error";
  }
  if (e instanceof TypeError) {
    // fetch failed entirely (connection refused, DNS, etc).
    return "backend-down";
  }
  return "unknown";
}
```

Then the existing per-card `catch (e) => toast.error("Failed…")`
calls upgrade to:

```tsx
.catch((e) => {
  const kind = classifyBackendError(e);
  toast.error("Failed to load X", {
    description: backendErrorMessage(kind, e),
    action: backendErrorAction(kind) ? {
      label: "Open docs",
      onClick: () => openDocs("/docs/SECURITY-HARDENING"),
    } : undefined,
  });
});
```

### 5. Right-rail collapse (review item #4)

Today the right rail (Signal / Avatar / Voice / System) shows
empty/zero state when healthy. Collapse by default:

```tsx
// frontend/src/components/layout/CockpitLayout.tsx — right rail
const [railExpanded, setRailExpanded] = useState(false);

return (
  <div className="flex">
    <main className="flex-1">{/* cockpit content */}</main>
    <aside className={cn(
      "border-l border-border transition-all",
      railExpanded ? "w-80" : "w-12",  // collapsed = just a tab strip
    )}>
      <button onClick={() => setRailExpanded(!railExpanded)}>
        {railExpanded ? "→" : "←"}
      </button>
      {railExpanded && <StatusRail />}
    </aside>
  </div>
);
```

Default collapsed. Click → slide out. Persist `railExpanded` to
localStorage so it survives reload.

### 6. Persistent breadcrumb / "← Home" (review item #12)

```tsx
// frontend/src/components/layout/Breadcrumb.tsx NEW (~40 LoC)

export function Breadcrumb() {
  const location = useLocation();
  if (location.pathname === "/") return null;  // home page is implicit
  const segments = location.pathname.split("/").filter(Boolean);
  return (
    <nav className="text-[10px] font-mono text-text-muted">
      <Link to="/">⌂ Home</Link>
      {segments.map((seg, i) => (
        <Fragment key={i}>
          <span className="mx-1">/</span>
          <Link to={`/${segments.slice(0, i + 1).join("/")}`}>
            {seg}
          </Link>
        </Fragment>
      ))}
    </nav>
  );
}
```

Mount in `CockpitLayout` + `MobileLayout` top header.

### 7. Doc: dev-mode `HALO_TEST_AUTH_BYPASS` (review item — security #5)

```markdown
# Dev workflow (Sprint 49)

To run the full stack locally WITHOUT setting up the bearer
token (for UI iteration / design work):

```bash
# Terminal 1: backend with test auth bypass
cd ~/workspace/working/gundam-halo/backend
HALO_TEST_AUTH_BYPASS=true HALO_HOME=$HOME/.gundam-halo MINIMAX_API_KEY=test \
    .venv/bin/python -m uvicorn app.main:halo_app --host 127.0.0.1 --port 8765

# Terminal 2: vite dev server
cd ~/workspace/working/gundam-halo/frontend
./node_modules/.bin/vite

# Browser: http://localhost:5173/
```

The Tauri shell is NOT needed — the SPA runs in plain Chromium.
The `authedRequest()` wrapper silently skips bearer injection
when `window.__haloApiToken` is unset, and `HALO_TEST_AUTH_BYPASS`
turns off the bearer check on the backend. Read-side endpoints
work without auth. Write-side endpoints work too (bypass).
```

Append to `docs/SECURITY-HARDENING.md` (new section after the
"Backward compatibility" block).

## Files to create / modify

### Config (~10 LoC)
- `frontend/vite.config.ts` — fix proxy port (8765).

### Frontend (~600 LoC)
- `frontend/src/lib/api.ts` — `requestJson` + `requestText`
  split + `res.clone()` fix; `API_BASE` default to `window.location.origin`.
- `frontend/src/components/layout/CockpitLayout.tsx` —
  3-state machine (`loading | ready | offline`); skeleton
  grid; offline banner; right-rail collapse.
- `frontend/src/components/layout/Breadcrumb.tsx` NEW (~40 LoC).
- `frontend/src/components/layout/MobileLayout.tsx` — add
  breadcrumb mount.
- `frontend/src/lib/backend-error.ts` NEW (~60 LoC) —
  `classifyBackendError` + `backendErrorMessage` +
  `backendErrorAction` helpers.
- Per-card update: `HeldOutEvalCard.tsx`,
  `SetupWizard.tsx`, `BackendHealthBanner.tsx` —
  upgrade `catch (e) => toast.error(...)` to use
  `classifyBackendError` + docs-link action (~50 LoC total).

### Docs (~250 LoC)
- `docs/FEATURE-SPEC-SPRINT49-UI-ROBUSTNESS.md` (this file).
- `docs/CHANGELOG.md` [Unreleased] entry.
- `docs/SECURITY-HARDENING.md` — add "Dev workflow
  (`HALO_TEST_AUTH_BYPASS`)" section.

### Tests (~12 new tests)
- `frontend/src/lib/api.test.ts` NEW (~80 LoC, 4 tests):
  - `test_api_base_defaults_to_window_origin_when_no_env_var`.
  - `test_requestJson_uses_res_clone_so_text_fallback_works` (mock
    fetch returning a Response whose .json() succeeds AND .text()
    is also called — verifies the body isn't locked).
  - `test_requestText_returns_raw_body`.
  - `test_ApiError_carries_status_and_body`.
- `frontend/src/lib/backend-error.test.ts` NEW (~70 LoC, 4 tests):
  - `test_classifyBackendError_503_is_auth_missing`.
  - `test_classifyBackendError_401_is_auth_invalid`.
  - `test_classifyBackendError_502_is_backend_down`.
  - `test_classifyBackendError_TypeError_is_backend_down`.
- `frontend/src/components/layout/CockpitLayout.test.tsx` NEW
  (~80 LoC, 2 tests):
  - `test_cockpit_renders_skeleton_during_loading_not_blank` (the
    OLD behaviour was an empty "LOADING…" string; verify the
    new behaviour renders the skeleton grid).
  - `test_cockpit_shows_offline_banner_when_backend_unreachable`.
- `frontend/src/components/layout/Breadcrumb.test.tsx` NEW (~50
  LoC, 2 tests):
  - `test_breadcrumb_hidden_on_home`.
  - `test_breadcrumb_segments_correct_for_nested_route`.

## Acceptance criteria

- [ ] Fresh clone + `npm install` + dev backend → cockpit renders
  shell + skeletons within 200 ms; first data card populates
  within 5 s or shows offline banner (not frozen LOADING).
- [ ] With backend on port 8765 + vite proxy fixed → all SPA
  fetches succeed without absolute-URL overrides.
- [ ] With `HALO_TEST_AUTH_BYPASS=true` set on backend → no
  `HALO_API_TOKEN` needed; all endpoints respond 200.
- [ ] With `HALO_API_TOKEN` unset + bypass off → offline banner
  explains "Run `scripts/generate-auth-token.sh`" with link.
- [ ] `/settings` + `/audit` no longer throw `body stream already
  read` on initial load.
- [ ] Right rail default-collapsed; click to expand.
- [ ] Breadcrumb shows on `/projects/...`, `/settings`, `/audit`,
  `/setup` (not on `/`).
- [ ] Full backend pytest stays green (no backend changes).
- [ ] Frontend tsc 0 errors + vitest +12 new tests
  (104 → 116).
- [ ] `cargo check --tests` clean (no Rust changes — verify only).

## Version bump

`__version__` 0.1.20 → **0.1.21** (PATCH per Mavis memory rule —
bugfix + UI polish; no new user-facing feature). 4 surfaces synced.

## Out of scope (deferred to future sprints)

- **Theme switcher hover-preview** (review item #7) — Sprint 50.
- **Tab sidebar in `/settings`** (review item #9) — Sprint 50.
- **Mobile iPhone Safari spot-check recipe** (review item — mobile
  audit) — Sprint 50.
- **Storybook-style component gallery** (review item — design
  system docs) — Sprint 51.
- **Live2D hydration in avatar card** (review item — long-term) —
  Sprint 52+.
- **Audit log stream merge** (review item — auth log + mac control
  log) — Sprint 52.
- **Orphaned component audit** (review item — 30+ components,
  many unwired) — Sprint 51.

## Why this is the right minimal surface

5 P0 bugs + 2 medium-impact polish items, all in the frontend
(+ 1 dev-config line + 1 doc). No backend changes. No Rust
changes. Total ~860 LoC across ~10 files. Fits in 1 focused
sprint.

The review surfaced 12 items total; Sprint 49 picks the 7 with
the highest user-impact-to-effort ratio. The other 5 are scoped
explicitly to Sprint 50+ so they're not forgotten.
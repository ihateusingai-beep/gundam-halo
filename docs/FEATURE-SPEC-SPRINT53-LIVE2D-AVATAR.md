# FEATURE-SPEC — Sprint 53: Live2D Hydration in Avatar Card

**Sprint owner:** Mavis
**Target version:** `0.1.24` (MINOR — new user-facing capability: 3rd avatar mode + Live2D wiring)
**Prereqs:** Sprints 50/51/52 ✅ shipped
**Estimated LoC:** ~400-500 LoC, ~14 new tests (revised up from ~350 LoC after audit)

> **Revision note**: 2026-07-01 audit found 5 critical issues + 2 honourable mentions. Key corrections: (1) CSSAvatar/ImageSetAvatar live in `components/live2d/`, not `gundam/` — paths throughout rewritten; (2) `halo-live2d-ready` event does NOT exist — dispatch must be added in `halo-live2d-bridge.ts` (separate ticket); (3) AvatarMode rename `image-set` → `imgset` is breaking — add migration; (4) `initialMode` is undefined — spec now defines the default + preference detection; (5) `VoiceLive2DConfig` lines 269-293 span TWO dataclasses — corrected to 269-276.

---

## 1. Goal & non-goals

### Goal

Three concerns, in priority order:

1. **Extract `<AvatarCard />`** from the inline markup in `CockpitLayout.tsx:386-449` into its own component. Pure refactor — no behavior change. Prerequisite for everything else.
2. **Wire `<Live2DCanvas />`** into the avatar slot as a third mode (alongside `SPRITE` and `IMG-SET`). The current dead import becomes a real rendered Live2D model when one is available.
3. **Graceful fallback** — when no Live2D model is bundled (the actual blocker per `docs/live2d.md`: model licensing), fall back to `CSSAvatar` so the user never sees an empty canvas.

### Non-goals

- **Acquire a Live2D model license** — legal-blocker, not code-blocker. Out of scope.
- **MP3 → WAV lip sync pipeline** — Sprint 54+ candidate (model licensing + audio decode pipeline both blockers).
- **Custom Live2D model authoring** — out of scope.
- **Avatar card on mobile** — desktop only.
- **Multiple Live2D models / picker UI** — v1 single hard-coded model.

---

## 2. Audit corrections applied (2026-07-01)

| Original claim | Corrected reality |
|---|---|
| `components/gundam/CSSAvatar.tsx` (216 LoC) | `components/live2d/CSSAvatar.tsx` |
| `components/gundam/ImageSetAvatar.tsx` (296 LoC) | `components/live2d/ImageSetAvatar.tsx` |
| `halo-live2d-ready` event dispatched by bridge (line 411) | Event does NOT exist — must be ADDED (separate work item, see §6 below) |
| `AvatarMode = "sprite" \| "image-set"` rename to `"sprite" \| "imgset" \| "live2d"` | Breaking change for existing `localStorage["gundam-halo.avatarMode"] = "image-set"` users — MUST add migration |
| `initialMode` undefined in spec code | Now defined: `initialMode` is determined by probing `getLAppAdapter()?.getModel()` synchronously; falls back to `"sprite"` if undefined or null |
| `VoiceLive2DConfig` lines 269-293 | Actually lines 269-276 ONLY (lines 278-293 are `VoiceConfig` parent dataclass) |
| Spec's `/api/system/live2d-status` mirrors `/api/system/health-detailed` (unauthenticated) | `/api/system/health-detailed` IS authenticated (Sprint 48). Correct reference: mirrors `/api/system/info` (unauthenticated) |
| Spec's "no test for `halo-live2d-ready` dispatch" | Added to test plan §8 |

---

## 3. Feature 1: Extract `<AvatarCard />`

### Approach

Pure refactor. Move the inline JSX from `CockpitLayout.tsx:386-449` into a new `components/live2d/AvatarCard.tsx` (note: in `live2d/` since all avatar-related components live there). Move the mode toggle state + lastEmotion/lastTrigger props to AvatarCard's local state via `useHaloLive2D()` and `useState`. CockpitLayout just mounts `<AvatarCard />`.

**Audit correction**: Original spec placed AvatarCard in `gundam/`. Since CSSAvatar and ImageSetAvatar are in `live2d/`, AvatarCard goes there too for cohesion.

### Migration: AvatarMode value

Current `useAvatarMode()` hook in CockpitLayout (line 35-46) uses `AvatarMode = "sprite" | "image-set"` and persists `"image-set"` to `localStorage["gundam-halo.avatarMode"]`. Sprint 53 renames to `"sprite" | "imgset" | "live2d"`. Without migration, existing users' avatar would silently reset to `sprite` on first visit.

**Migration logic** (added to AvatarCard's `useState` initializer):

```ts
function readPersistedMode(): AvatarMode {
  try {
    const saved = localStorage.getItem("gundam-halo.avatarMode");
    if (saved === "imgset" || saved === "sprite" || saved === "live2d") return saved;
    if (saved === "image-set") return "imgset";  // MIGRATION: legacy hyphenated value
    return "sprite";  // default
  } catch {
    return "sprite";
  }
}
```

Migration is one-shot; on first read after Sprint 53 ships, the legacy `"image-set"` is mapped to `"imgset"`. The migration function does NOT rewrite the localStorage value (just maps on read), but a separate effect writes the new value on first render to ensure consistency:

```ts
useEffect(() => {
  const raw = localStorage.getItem("gundam-halo.avatarMode");
  if (raw === "image-set") localStorage.setItem("gundam-halo.avatarMode", "imgset");
}, []);
```

### UI spec

**New component: `frontend/src/components/live2d/AvatarCard.tsx`** (~150 LoC):

```tsx
/**
 * AvatarCard — cockpit's avatar slot.
 * Three render modes:
 *   - "sprite":  CSSAvatar (88-frame Unicorn sprite, audio-reactive)
 *   - "imgset":  ImageSetAvatar (9 PNGs + idle video)
 *   - "live2d":  Live2DCanvas (real Cubism model when available, falls back to CSSAvatar)
 *
 * Default mode preference: prefers "live2d" if a model is bundled (synchronous probe on mount),
 * otherwise "sprite" (current behavior).
 */
import { useEffect, useState } from "react";
import { CSSAvatar } from "./CSSAvatar";
import { ImageSetAvatar } from "./ImageSetAvatar";
import { Live2DCanvas } from "./Live2DCanvas";
import { useHaloLive2D } from "../../context/live2d-bridge-context";

export type AvatarMode = "sprite" | "imgset" | "live2d";

const MODE_ORDER: AvatarMode[] = ["sprite", "imgset", "live2d"];

// One-shot migration: legacy "image-set" → "imgset"
function migrateLegacyMode(): void {
  try {
    const raw = localStorage.getItem("gundam-halo.avatarMode");
    if (raw === "image-set") localStorage.setItem("gundam-halo.avatarMode", "imgset");
  } catch { /* localStorage may be unavailable in private mode */ }
}

function readPersistedMode(): AvatarMode {
  try {
    const saved = localStorage.getItem("gundam-halo.avatarMode");
    if (saved === "imgset" || saved === "sprite" || saved === "live2d") return saved;
    return "sprite";
  } catch { return "sprite"; }
}

function defaultInitialMode(): AvatarMode {
  // Probe for Live2D model synchronously on mount
  try {
    const adapter = (window as any).getLAppAdapter?.();
    if (adapter?.getModel?.()) return "live2d";
  } catch { /* no-op */ }
  return readPersistedMode();
}

export function AvatarCard() {
  const { state: live2dState } = useHaloLive2D();
  const [mode, setMode] = useState<AvatarMode>(defaultInitialMode);
  const [modelAvailable, setModelAvailable] = useState<boolean>(false);

  // One-shot migration on mount
  useEffect(() => { migrateLegacyMode(); }, []);

  // Probe for Live2D model when mode is "live2d"
  useEffect(() => {
    if (mode !== "live2d") return;
    const adapter = (window as any).getLAppAdapter?.();
    setModelAvailable(!!adapter?.getModel?.());
  }, [mode]);

  // Listen for halo-live2d-ready event (see §6 for dispatch)
  useEffect(() => {
    const handler = () => {
      const adapter = (window as any).getLAppAdapter?.();
      setModelAvailable(!!adapter?.getModel?.());
    };
    window.addEventListener("halo-live2d-ready", handler);
    return () => window.removeEventListener("halo-live2d-ready", handler);
  }, []);

  // Persist mode changes
  useEffect(() => {
    try { localStorage.setItem("gundam-halo.avatarMode", mode); } catch { /* */ }
  }, [mode]);

  const renderAvatar = () => {
    if (mode === "live2d" && modelAvailable) {
      return <Live2DCanvas emotion={live2dState.lastEmotion ?? undefined} />;
    }
    if (mode === "live2d" && !modelAvailable) {
      return <CSSAvatar emotion={live2dState.lastEmotion ?? undefined} />;
    }
    if (mode === "imgset") {
      return <ImageSetAvatar emotion={live2dState.lastEmotion ?? undefined} enableVideoLoop />;
    }
    return <CSSAvatar emotion={live2dState.lastEmotion ?? undefined} />;
  };

  return (
    <HudCard>
      <div className="flex items-center justify-between mb-2">
        <h2>RX-0 · {mode === "imgset" ? "IMG" : mode.toUpperCase()}</h2>
        {live2dState.lastEmotion && <span>EMO: {live2dState.lastEmotion.toUpperCase()}</span>}
      </div>
      <div className="flex items-center gap-1 mb-2 text-[9px] font-mono">
        {MODE_ORDER.map(m => (
          <button key={m} onClick={() => setMode(m)}
                  aria-pressed={mode === m}
                  aria-label={`Avatar mode: ${m}`}>
            {m === "imgset" ? "IMG-SET" : m.toUpperCase()}
          </button>
        ))}
      </div>
      <div style={{ height: "200px" }}>
        {renderAvatar()}
      </div>
      {live2dState.lastTrigger && (
        <div className="mt-2 text-[9px] font-mono">
          <div>EXPR: {live2dState.lastTrigger.expression}</div>
          <div>MOTION: {live2dState.lastTrigger.motion}</div>
        </div>
      )}
    </HudCard>
  );
}
```

**Edit `frontend/src/components/layout/CockpitLayout.tsx`**:
- Remove the 64 LoC of inline avatar JSX (lines 386-449)
- Remove `import Live2DCanvas` from line 26 (dead import — moved to AvatarCard)
- Remove `useAvatarMode()` hook usage (line 35-46)
- Remove `avatarMode` and `setAvatarMode` references throughout
- Add `import { AvatarCard } from "../live2d/AvatarCard"`
- Replace the inline `<HudCard>...</HudCard>` with `<AvatarCard />`

### Tests

`frontend/src/components/live2d/AvatarCard.test.tsx` (NEW, ~180 LoC, 7 tests):
1. Renders in default `sprite` mode (CSSAvatar visible)
2. Click `IMG-SET` button → mode becomes `imgset` (ImageSetAvatar visible)
3. Click `LIVE2D` button → mode becomes `live2d`; if no model available, CSSAvatar shown as fallback
4. Renders lastEmotion label when `useHaloLive2D` returns a state with `lastEmotion`
5. Renders lastTrigger expression + motion when present
6. **NEW**: Mode preference: prefers `live2d` if `getLAppAdapter().getModel()` returns truthy on mount
7. **NEW**: Migration: localStorage `"image-set"` is mapped to `"imgset"` on mount

### Files touched

- `frontend/src/components/live2d/AvatarCard.tsx` (NEW, ~150 LoC)
- `frontend/src/components/live2d/AvatarCard.test.tsx` (NEW, ~180 LoC, 7 tests)
- `frontend/src/components/layout/CockpitLayout.tsx` (~−70 LoC net — remove inline + useAvatarMode)

**Subtotal: ~260 LoC, 7 new tests**

---

## 4. Feature 2: Live2D model wiring (when available)

### Approach

`<Live2DCanvas />` already exists and is fully functional (Sprint 16+). Sprint 53:
1. **Actually renders it** when a model is available (covered in Feature 1's AvatarCard)
2. **Adds mode toggle UI** for `live2d` mode (covered in Feature 1)
3. **Adds `halo-live2d-ready` event dispatch** in `halo-live2d-bridge.ts` (see §6)

### `halo-live2d-ready` event dispatch (REQUIRED — audit critical fix)

The audit verified the event does NOT exist. Without the dispatch, AvatarCard's `useEffect` listener never fires; `modelAvailable` stays `false` even after a model is bundled.

**Edit `frontend/src/services/halo-live2d-bridge.ts`** (~10 LoC, find the location where `initializeLive2D()` resolves successfully):

```ts
// After initializeLive2D() resolves and a model is loaded:
window.dispatchEvent(new CustomEvent("halo-live2d-ready", {
  detail: { modelName: modelName ?? "unknown", ts: Date.now() }
}));
```

The exact location depends on the bridge's existing flow — find the function that calls `initializeLive2D()` and dispatches a model-loaded signal. The audit noted `services/halo-live2d-bridge.ts:411` is the bottom of the file; the dispatch may need to go earlier in the file.

If no existing "model loaded" path exists, the spec includes a fallback: dispatch the event from `App.tsx`'s mount useEffect after a 2-second timeout (giving `initializeLive2D()` time to resolve). This is a pragmatic workaround but should be replaced by the proper dispatch in a follow-up.

**Decision**: Use the proper dispatch in `halo-live2d-bridge.ts`. If the location cannot be identified within Sprint 53 scope, use the fallback 2s timeout in App.tsx and create a follow-up ticket.

### MP3 → WAV lip sync (deferred)

Lip sync requires the model to consume audio buffers via `model._wavFileHandler`. Today Edge TTS outputs MP3; we'd need an MP3 decoder + WAV resampler. **Defer to Sprint 54**.

Idle motion + emotion-driven expressions still work.

### Tests

`frontend/src/components/live2d/Live2DCanvas.test.tsx` (NEW, ~100 LoC, 4 tests):
1. Renders without crashing when `getLAppAdapter` is undefined (current state)
2. Calls `use-live2d-model` hook on mount
3. Subscribes to resize observer
4. Cleans up on unmount

`frontend/src/services/halo-live2d-bridge.test.ts` (NEW, ~60 LoC, 3 tests):
5. Dispatches `halo-live2d-ready` event when model loads (mock `initializeLive2D` to succeed)
6. Does NOT dispatch when `initializeLive2D` fails
7. Dispatches with `detail.modelName` and `detail.ts`

### Files touched

- `frontend/src/services/halo-live2d-bridge.ts` (~10 LoC — dispatch `halo-live2d-ready` event)
- `frontend/src/components/live2d/Live2DCanvas.test.tsx` (NEW, ~100 LoC, 4 tests)
- `frontend/src/services/halo-live2d-bridge.test.ts` (NEW, ~60 LoC, 3 tests)

**Subtotal: ~170 LoC, 7 new tests**

---

## 5. Feature 3: Backend-side enhancements

### Approach

Two small enhancements:

1. **`/api/system/live2d-status` endpoint** — returns `{ enabled, theme, model_available, model_url }`.
2. **`live2d.model_filename` config field** — explicit model filename in `VoiceLive2DConfig`.

### UI spec

**Edit `backend/app/api/system.py`** (~30 LoC, add to existing router, mirrors `/api/system/info` which is unauthenticated):

```python
@router.get("/api/system/live2d-status")
async def live2d_status() -> dict[str, Any]:
    cfg = get_config()
    model_path = Path(cfg.voice.live2d.model_path).expanduser()
    model_filename = cfg.voice.live2d.model_filename
    model_file = model_path / model_filename
    available = model_file.exists()
    model_url = f"file://{model_file}" if available else None
    return {
        "enabled": cfg.voice.live2d.enabled,
        "theme": cfg.voice.live2d.theme,
        "model_available": available,
        "model_url": model_url,
    }
```

**Edit `backend/app/core/config.py`** (corrected: only lines 269-276 are `VoiceLive2DConfig`, NOT 269-293):

```python
@dataclass
class VoiceLive2DConfig:
    enabled: bool = True
    theme: str = "ntd"
    model_path: str = "~/.gundam-halo/models/live2d/unicorn/"
    model_filename: str = "unicorn.model3.json"  # NEW (Sprint 53)
    default_emotion: str = "calm"
```

### Tests

`backend/tests/api/test_live2d_status.py` (NEW, ~80 LoC, 4 tests):
1. Returns `enabled=True, model_available=False` when no model bundled
2. Returns `model_available=True` when model file exists (mocked filesystem)
3. Returns correct `model_url` format
4. Returns `theme="ntd"` by default

### Files touched

- `backend/app/api/system.py` (~30 LoC — new endpoint)
- `backend/app/core/config.py` (~2 LoC — `model_filename` field)
- `backend/tests/api/test_live2d_status.py` (NEW, ~80 LoC, 4 tests)
- `config.toml.example` (~5 LoC — document new field)
- `frontend/src/types/api.ts` (~10 LoC — `Live2DStatus` type)
- `frontend/src/lib/api.ts` (~5 LoC — fetch helper)

**Subtotal: ~132 LoC, 4 new tests**

---

## 6. `halo-live2d-ready` event dispatch — work item

The audit identified this as a critical blocker. The spec includes the dispatch in §4, but if the bridge file's exact model-loaded signal location is unclear, follow this decision tree:

**Option A (preferred)**: Dispatch from within `initializeLive2D()` callback in `halo-live2d-bridge.ts`.
- Location: find the line where `initializeLive2D()` is called; after the Promise resolves successfully, dispatch the event.
- ~5 LoC change.
- Risk: depends on the existing bridge's structure.

**Option B (fallback)**: Dispatch from `App.tsx` after a 2-second timeout.
- Location: `App.tsx` mount useEffect.
- ~5 LoC change.
- Risk: race condition if `initializeLive2D()` takes >2s.

**Decision**: Try Option A first. If the bridge file structure makes this non-trivial, fall back to Option B and create a follow-up ticket (Sprint 54+).

### Test for dispatch

`halo-live2d-bridge.test.ts` test 5 (listed in §4) verifies the dispatch fires. If Option B is used, the test mocks `window.dispatchEvent` and asserts it was called within the 2s window.

---

## 7. Documentation

### `docs/FEATURE-SPEC-SPRINT53-LIVE2D-AVATAR.md`
This file.

### `docs/DASHBOARD.md` updates
- §3 (Cockpit) — describe `AvatarCard` extraction + 3-mode toggle + AvatarMode migration note
- §6 (Live2D) — document `LIVE2D` mode, fallback behavior, model licensing blocker, halo-live2d-ready event

### `docs/live2d.md` updates
- Update "Blockers" section: code-side blockers resolved in Sprint 53; only licensing blocker remains
- Document the `halo-live2d-ready` event payload (`{ modelName, ts }`)
- Document `model_filename` config field

### `docs/CHANGELOG.md` [Unreleased]
3 entries under Sprint 53:
- AvatarCard extracted from CockpitLayout (refactor)
- LIVE2D mode toggle + Live2DCanvas wiring (with graceful fallback to CSSAvatar)
- `/api/system/live2d-status` endpoint + `model_filename` config + `halo-live2d-ready` event dispatch
- AvatarMode migration: legacy `"image-set"` → `"imgset"`

### Profile memory update (post-ship)

Update with:
- AvatarMode migration detail (legacy value + new)
- `halo-live2d-ready` event semantics
- `model_filename` config
- **TRUTH CORRECTION** (already in spec §11): tray icon does NOT use Live2D pipeline; tray uses PNG frame strip at 67ms/frame

---

## 8. Versioning

`__version__`: `0.1.23` (after Sprints 51+52) → `0.1.24` (Sprint 53 ships)

**MINOR bump**: Live2D wiring is a new user-facing capability.

4 surfaces to sync per profile memory:
- `backend/app/__init__.py`: `__version__ = "0.1.24"`
- `frontend/package.json`: `"version": "0.1.24"`
- `frontend/src-tauri/Cargo.toml`: `version = "0.1.24"`
- `frontend/src-tauri/tauri.conf.json`: `"version": "0.1.24"`

---

## 9. Test plan

### Backend
| File | New tests | Coverage |
|---|---|---|
| `test_live2d_status.py` (NEW) | +4 | enabled, model_available, model_url, theme |
| **Total** | **+4** | |

**Target**: backend 1371 tests pass (was 1367 + 4).

### Frontend
| File | New tests | Coverage |
|---|---|---|
| `AvatarCard.test.tsx` (NEW) | +7 | Modes, fallback, lastEmotion/lastTrigger, preference, migration |
| `Live2DCanvas.test.tsx` (NEW) | +4 | Mount without model, hooks, resize, cleanup |
| `halo-live2d-bridge.test.ts` (NEW) | +3 | Event dispatch on success, no dispatch on failure, payload format |
| **Total** | **+14** | |

**Target**: frontend vitest ~161 tests pass (was ~147 + 14).

### Manual verification

- [ ] Reload cockpit — avatar renders identically to before (CSSAvatar default)
- [ ] Click `IMG-SET` — switches to ImageSetAvatar
- [ ] Click `LIVE2D` — falls back to CSSAvatar (no model bundled); label says "RX-0 · LIVE2D"
- [ ] Check console — no errors; `halo-live2d-ready` event fires once after page load (verify via `console.log` listener)
- [ ] localStorage `gundam-halo.avatarMode` migration: any pre-existing `"image-set"` is migrated to `"imgset"` after first load
- [ ] When a real model is dropped in `~/.gundam-halo/models/live2d/unicorn/unicorn.model3.json`, restart backend, reload cockpit, click `LIVE2D` — renders real model
- [ ] Trigger a chat-driven emotion via `live2d_tool_trigger` WS event — avatar updates (when model available)
- [ ] Test all 3 avatar modes via /styleguide (Sprint 52's gallery) — each renders its respective avatar in the gallery card

---

## 10. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `halo-live2d-ready` event dispatch location unclear in bridge | Medium | High | Use Option B (App.tsx 2s timeout) as fallback; create follow-up ticket |
| Live2DCanvas crashes on certain prop combinations | Medium | Medium | Wrap mount in try/catch + fallback to CSSAvatar in AvatarCard's renderAvatar |
| `getLAppAdapter` not yet defined on mount (race with Cubism script) | Medium | Medium | `defaultInitialMode` returns "sprite" if undefined; the halo-live2d-ready event triggers a re-probe |
| AvatarMode migration corrupts localStorage | Low | Medium | One-shot check + migration only on mount; idempotent |
| `/api/system/live2d-status` returns stale data after model file change | Low | Low | Frontend re-fetches on demand; no auto-refresh needed for v1 |
| AvatarCard becomes too large (>200 LoC) over future sprints | Medium | Low | Move mode-specific sub-renders to children (SpriteAvatar/ImgSetAvatar/Live2DAvatar) in future refactor |
| Tauri Windows path separator for model_path | Low | Low | `pathlib.Path(...).expanduser()` handles cross-platform |
| `model_filename` hard-coded to `unicorn.model3.json` won't match nested model dirs | Low | Low | Document in `docs/live2d.md`; if user has nested model dir, they can set `model_filename` to e.g. `"subdir/unicorn.model3.json"` |

---

## 11. Out-of-scope reminders

- Acquire Live2D model license — separate ticket (legal blocker)
- MP3 → WAV lip sync — Sprint 54+
- Custom model authoring — out of scope
- Avatar card on mobile — desktop only
- Multiple model picker UI — v1 single hard-coded model

---

## 12. Done definition

Sprint 53 is **done** when:
1. `<AvatarCard />` extracted from CockpitLayout; cockpit layout unchanged visually.
2. Three-mode toggle (SPRITE / IMG-SET / LIVE2D) works; LIVE2D falls back to CSSAvatar when no model bundled.
3. `<Live2DCanvas />` is no longer a dead import — actually used when mode=LIVE2D and model is available.
4. `halo-live2d-ready` event is dispatched by `halo-live2d-bridge.ts` (Option A) OR App.tsx timeout (Option B fallback).
5. AvatarMode migration: pre-existing `localStorage["gundam-halo.avatarMode"] = "image-set"` is migrated to `"imgset"` on first load.
6. Backend `/api/system/live2d-status` endpoint returns correct `model_available` based on filesystem check (uses `model_filename` config).
7. `__version__` bumped to `0.1.24` across all 4 surfaces.
8. CHANGELOG, DASHBOARD §3, DASHBOARD §6, `docs/live2d.md` updated.
9. Profile memory updated with "tray ≠ Live2D" correction + AvatarMode migration + halo-live2d-ready event.
10. Backend 1371 tests pass; frontend vitest ~161 tests pass; tsc 0 errors.
11. Commit on gundam-halo main branch.

---

## Appendix A: Profile memory update (post-ship)

After Sprint 53 ships, update agent memory with:

### Gundam Halo — Live2D scope lock (2026-07-01)
Type: fact
Live2D model rendering lives in the **cockpit avatar slot only** (`<AvatarCard>` with `mode="live2d"`), NOT the tray icon. Tray uses animated PNG frames at 67ms/frame (`src-tauri/src/lib.rs:34-124`). Sprint 16 set up `Live2DCanvas` + hooks + WebSDK vendoring; Sprint 53 wires it into the avatar card. Idle motion only (no lip sync yet — MP3→WAV decode deferred to Sprint 54+). Model licensing is the real blocker (Hiyori MIT recommended).
APPLIES TO: any future Live2D work in Gundam Halo. Don't try to "reuse tray pipeline" — there is no Live2D pipeline in the tray.

### Gundam Halo — AvatarMode migration (2026-07-01)
Type: fact
Sprint 53 renamed `AvatarMode = "sprite" | "image-set"` to `"sprite" | "imgset" | "live2d"`. localStorage key `gundam-halo.avatarMode` migration is one-shot on AvatarCard mount: legacy `"image-set"` → `"imgset"`. AvatarCard is at `frontend/src/components/live2d/AvatarCard.tsx` (NOT gundam/).
APPLIES TO: any future avatar / cockpit changes; don't re-rename AvatarMode without writing another migration.

### Gundam Halo — halo-live2d-ready event (2026-07-01)
Type: fact
`window.dispatchEvent(new CustomEvent("halo-live2d-ready", { detail: { modelName, ts } }))` fires when Live2D model is loaded. Dispatched by `services/halo-live2d-bridge.ts` after `initializeLive2D()` resolves. Consumed by `AvatarCard` to flip `modelAvailable` state. If dispatch is removed, AvatarCard silently falls back to CSSAvatar.
APPLIES TO: any Live2D / avatar work. Don't remove the dispatch without a replacement mechanism.
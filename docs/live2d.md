# Live2D Integration (M3)

> Last updated: 2026-06-07

## Status

CSS Avatar fallback deployed. Full WS pipeline wired. Real Live2D model blocked by licensing.

## CSS Avatar (live)

`src/components/live2d/CSSAvatar.tsx` + `src/styles/gundam.css` (~300 lines).

8 emotion states driven by CSS class changes:
- calm / focused / psychoframe / alert / damage / resolve / jubilant / stealth
- Each state: unique eye animation, head animation, color palette, psychoframe glow

Data flow:
```
Backend: [EMO:awakening] text
  → voice_ws.py emits { type: "live2d.trigger", data: {emotion, expression, motion} }
  → halo-live2d-bridge.ts subscribes to WS events
  → CSSAvatar adds .avatar--psychoframe class
  → CSS transition → pink glow, fast 0.8s pulse
```

Test via browser console:
```javascript
__haloLive2D.triggerLive2D("ntd_psychoframe", "awaken")
__haloLive2D.triggerLive2D("ntd_damage", "flinch")
__haloLive2D.triggerLive2D("ntd_stealth", "vanish")
```

## WebSDK Integration Pattern

**Problem**: WebSDK TypeScript files use path alias `@cubismsdksamples/main` pointing to local files. Vite Rollup fails to resolve them with "Rollup failed to resolve import".

**Solution**: Access WebSDK via `window` globals instead of TypeScript imports.

- WebSDK loaded via `<script>` tags in `main.tsx` (before React mounts)
- `live2dcubismcore.min.js` → sets `window.Live2DCubismCore`
- `initializeLive2D()` → sets `window.initializeLive2D`, `window.getLAppAdapter`, `window.getLive2DManager`
- Hooks access via: `const getLAppDelegate = () => (window as any).LAppDelegate`
- NO direct TypeScript imports from WebSDK in hooks

Files adapted: `use-live2d-model.ts`, `use-live2d-resize.ts`

## Backend Files (M3)

| File | Purpose |
|------|---------|
| `app/voice/live2d/model_metadata.py` | Parse `.model3.json`, extract expressions/motions, validate mappings |
| `app/voice/live2d/ntd_responder.py` | `NTDResponder` implements `Live2DInterface` — validates + emits `Live2DTrigger` |
| `app/voice/live2d/live2d_factory.py` | `create_live2d()` → NTDResponder (replaced M1 NotImplementedError) |
| `app/api/voice_ws.py` | Emits `live2d.trigger` WS frame before TTS stream |
| `tests/voice/test_live2d.py` | 14 tests (metadata parsing, NTDResponder validation) |

## Frontend Files (M3)

| File | Purpose |
|------|---------|
| `src/services/halo-live2d-bridge.ts` | WS client to `/ws/voice`, subscribes to `live2d.trigger`, calls WebSDK |
| `src/context/live2d-bridge-context.tsx` | `HaloLive2DProvider` + `useHaloLive2D()` React hook |
| `src/context/live2d-config-context.tsx` | `Live2DConfigProvider` (model info state) |
| `src/context/live2d-types.ts` | `ModelInfo`, `EmotionMap`, `TapMotionMap` interfaces |
| `src/hooks/canvas/use-live2d-model.ts` | Model loading via window globals, drag/tap interaction |
| `src/hooks/canvas/use-live2d-resize.ts` | Canvas resize + scroll zoom |
| `src/hooks/canvas/use-live2d-expression.ts` | setExpression / resetExpression |
| `src/components/live2d/Live2DCanvas.tsx` | Live2D canvas (unused until real model) |
| `src/components/live2d/CSSAvatar.tsx` | CSS avatar (active) |

## Build Status

- Frontend: `tsc --noEmit` ✅, `vite build` ✅ (367KB JS)
- Backend: 160 tests pass ✅

## Blockers

1. **Live2D model** — Hiyori (MIT, recommended) or NT-D custom model. Model licensing is the real blocker, not the integration code.
2. **MP3 → WAV conversion** — Open-LLM-VTuber's lip sync expects WAV via `model._wavFileHandler`. Gundam Halo uses Edge TTS MP3 output. Need MP3→WAV decode or different lip sync approach.

## EMOTION_MAP (from halo_responder.py)

```
calm      → ntd_calm      + idle
focused   → ntd_focused   + lean_in
awakening → ntd_psychoframe + awaken
alert     → ntd_alert     + scan
damage    → ntd_damage    + flinch
resolve   → ntd_resolve   + stand
jubilant  → ntd_jubilant  + victory
stealth   → ntd_stealth   + vanish
```

CSS Avatar maps emotion strings (calm/awakening/etc.) to CSS classes (avatar--calm / avatar--psychoframe/etc.) directly — no expression/motion names needed.
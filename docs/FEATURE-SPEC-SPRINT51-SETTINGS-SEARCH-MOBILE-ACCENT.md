# FEATURE-SPEC — Sprint 51: Settings ⌘K Search + Mobile Drawer + Theme Accent Picker

**Sprint owner:** Mavis
**Target version:** `0.1.23` (MINOR — three new user-facing capabilities)
**Prereqs:** Sprint 50 ✅ shipped (settings sidebar + theme hover preview)
**Estimated LoC:** ~850-950 LoC, 22-25 new tests (revised up from ~700 LoC / 16 tests after audit)

> **Revision note**: 2026-07-01 audit found 6 critical issues in the initial draft. This revision addresses all of them. Key corrections: (1) `openPalette` parameter is `category` not `initialCategory`; (2) `?tab=` reader does NOT exist in `routes/settings/index.tsx` and must be added; (3) Custom accent + hover-preview requires NEW mechanism (toggle inline style on/off during hover, not always-set); (4) `ThemesTab.tsx` does NOT currently duplicate `ThemeHoverCard` — accent picker is added fresh; (5) `CommandPalette.test.tsx` does NOT exist — must be CREATED not extended; (6) theme store must use localStorage init pattern (lines 41/70 of theme.ts), NOT `onRehydrateStorage`.

---

## 1. Goal & non-goals

### Goal

Three polish capabilities on top of Sprint 50's settings sidebar:

1. **⌘K settings search** — open the existing global Command Palette filtered to "Settings" category from inside `/settings`. Currently users must scroll/jump through 8 tabs; with 8 tabs and frequent theme/memory/security tweaks this gets tedious.
2. **Mobile settings drawer** — bottom-sheet on `<768px` viewports, mirroring the desktop sidebar's 8 tabs in 2 groups. Sprint 50's mobile bottom nav currently navigates directly to `/settings` (no drawer UX); this adds the drawer pattern that DASHBOARD.md §3.5 always promised.
3. **Theme accent picker** — a single `Accent color` swatch row on the Themes tab that lets users override `--accent` globally (one hex color that overrides all theme presets).

### Non-goals

- New theme presets (still 8 — Sprint 36).
- Custom theme builder (whole CSS vars — out of scope; only `--accent` is customizable).
- Search filtering inside `/settings` tab content (e.g. VoiceTab search box) — eventual Sprint 51.x if users ask.
- Mobile gestures beyond tap (no swipe-between-tabs yet).
- Per-theme accent override — global only.

---

## 2. Audit corrections applied (2026-07-01)

| Original claim | Corrected reality | Source |
|---|---|---|
| `openPalette({ initialCategory })` | `openPalette({ category })` — `PaletteOpenEvent.category?: CommandCategory` | `CommandPalette.tsx:83-87` |
| `?tab=` reader "verify this already works" | Reader does NOT exist; must add `useSearchParams` + useEffect | `routes/settings/index.tsx:21-26` |
| Custom accent + hover-preview: "hover shows theme defaults" | Inline `style.setProperty` on `<html>` ALWAYS wins CSS cascade. Need toggle mechanism: remove inline style on hover-enter, restore on hover-leave | `ThemeHoverCard.tsx` setHoverTheme revert path |
| ThemesTab "duplicates ThemeHoverCard's live-preview" | ThemesTab has zero live-preview; simple click handlers only | `ThemesTab.tsx` |
| `CommandPalette.test.tsx` "extension" | File does NOT exist; must be CREATED | `ls frontend/src/components/gundam/CommandPalette.test.tsx` |
| Theme store uses `onRehydrateStorage` | Theme store does NOT use Zustand persist middleware; uses localStorage init at lines 41, 70 | `stores/theme.ts:41,70` |
| `routes/settings/index.tsx` test "NEW" file at `__tests__/search-button.test.tsx` | Existing tests in same dir as `SettingsSidebar.test.tsx`; follow that pattern | sibling pattern |

---

## 3. Feature 1: ⌘K settings search

### Approach

**Reuse existing `CommandPalette` (732 LoC)** — add a new "Settings" category group containing the 8 sidebar tabs as commands. Add a small `/settings` page-level trigger button that opens the palette pre-filtered to the Settings category. Add `?tab=` URL sync to `routes/settings/index.tsx` so deep-links from the palette actually navigate to the right tab.

### UI spec

**Edit 1: New palette commands** (`CommandPalette.tsx`, target area: existing `BUILTIN_COMMANDS` array):

```ts
// Add to CommandCategory union (around line 30):
export type CommandCategory =
  | "Navigation"
  | "Projects"
  | "Themes"
  | "Mac Control"
  | "System"
  | "Settings";  // NEW

// Add new category group:
{
  category: "Settings",
  commands: [
    { id: "settings.general",   title: "General",      subtitle: "User · LLM · Server paths",      icon: "◈", perform: () => navigate("/settings?tab=general") },
    { id: "settings.voice",     title: "Voice",        subtitle: "Wake · ASR · Corrector · Finetune", icon: "◍", perform: () => navigate("/settings?tab=voice") },
    { id: "settings.themes",    title: "Themes",       subtitle: "Theme + accent color",            icon: "◐", perform: () => navigate("/settings?tab=themes") },
    { id: "settings.memory",    title: "User Memory",  subtitle: "Per-user memory entries",         icon: "▣", perform: () => navigate("/settings?tab=memory") },
    { id: "settings.security",  title: "Security",     subtitle: "Auth · Audit log · Token",        icon: "⛨", perform: () => navigate("/settings?tab=security") },
    { id: "settings.mac",       title: "Mac Control",  subtitle: "File paths · Shell · A11y",       icon: "⚙", perform: () => navigate("/settings?tab=mac") },
    { id: "settings.secrets",   title: "Secrets",      subtitle: "API keys & tokens",               icon: "⚿", perform: () => navigate("/settings?tab=secrets") },
    { id: "settings.channels",  title: "Channels",     subtitle: "Telegram · Signal · Tailscale",   icon: "◉", perform: () => navigate("/settings?tab=channels") },
  ],
},
```

**Edit 2: Palette `openPalette()` extension** — already exists at line 95. Spec audit confirms it accepts `PaletteOpenEvent` with `category?: CommandCategory` (line 83-87). The current implementation reads `setCategoryFilter(ev?.category ?? null)` (line 384). **No new field needed; existing `category` works.**

**Edit 3: ⌘K button in `routes/settings/index.tsx`** (~15 LoC):
- Position: top-right of the settings page header
- 32×32px icon-only button labeled "⌘K"
- Click → `openPalette({ category: "Settings" })`
- ARIA: `aria-label="Search settings (Cmd+K)"`, `aria-keyshortcuts="Meta+K Control+K"`

**Edit 4: Add `?tab=` URL sync** to `routes/settings/index.tsx` (~20 LoC):

```tsx
import { useSearchParams } from "react-router";

// Inside SettingsPage:
const [searchParams, setSearchParams] = useSearchParams();
const tabFromUrl = searchParams.get("tab");
const [activeTab, setActiveTab] = useState<SettingsTab>(
  (isValidTab(tabFromUrl) ? tabFromUrl : "general") as SettingsTab
);

// Sync URL when activeTab changes (e.g. sidebar click)
const handleSetActiveTab = (tab: SettingsTab) => {
  setActiveTab(tab);
  setSearchParams({ tab }, { replace: true });
};

// Sync state when URL changes (e.g. palette deep-link)
useEffect(() => {
  const urlTab = searchParams.get("tab");
  if (urlTab && isValidTab(urlTab) && urlTab !== activeTab) {
    setActiveTab(urlTab as SettingsTab);
  }
}, [searchParams]);

// Replace {activeTab === ...} checks with handleSetActiveTab(tab)
```

`isValidTab` helper (8 lines):
```ts
function isValidTab(s: string | null): s is SettingsTab {
  return !!s && ["general", "voice", "themes", "memory", "security", "mac", "secrets", "channels"].includes(s);
}
```

**Pattern note**: `routes/projects/[id].tsx:58` uses `new URLSearchParams(window.location.search)` instead of `useSearchParams`. We use `useSearchParams` because SettingsPage is already inside `<Route>` so the hook is available.

### Tests

**`frontend/src/components/gundam/CommandPalette.test.tsx` (NEW, ~80 LoC, 4 tests)**:
1. Settings category appears with all 8 commands
2. `openPalette({ category: "Settings" })` filters to Settings category
3. Executing `settings.themes` command navigates to `/settings?tab=themes`
4. Pressing Escape with palette open closes it

**`frontend/src/routes/settings/index.test.tsx` (NEW sibling file, ~80 LoC, 4 tests)**:
5. ⌘K button click calls `openPalette({ category: "Settings" })` (mock spy)
6. URL `?tab=themes` on initial mount sets activeTab to "themes"
7. Clicking a tab via sidebar updates URL to `?tab=X`
8. Invalid `?tab=foo` defaults to "general"

### Files touched
- `frontend/src/components/gundam/CommandPalette.tsx` (~25 LoC — new Settings category)
- `frontend/src/components/gundam/CommandPalette.test.tsx` (NEW, ~80 LoC, 4 tests)
- `frontend/src/routes/settings/index.tsx` (~35 LoC — `?tab=` sync + ⌘K button + handleSetActiveTab)
- `frontend/src/routes/settings/index.test.tsx` (NEW, ~80 LoC, 4 tests)

**Subtotal: ~220 LoC, 8 new tests**

---

## 4. Feature 2: Mobile settings drawer

### Approach

New `<SettingsDrawer />` component mirroring `SettingsSidebar`'s structure but in a vertical 2×4 grid (touch-friendly) inside a bottom-sheet overlay. Slide-up animation; backdrop click / Escape / swipe-down dismiss. Mounted from `<MobileLayout />` when the user taps the bottom-nav Settings button (replaces the current `navigate("/settings")` behavior with `setDrawerOpen(true)`).

### UI spec

**Edit 1: Move `SIDEBAR_ENTRIES` to constants.ts** (`routes/settings/constants.ts`, ~15 LoC):

```ts
// Add to constants.ts
export interface SidebarEntry {
  id: SettingsTab;
  label: string;
  icon: string;
  group: "personalisation" | "system";
}

export const SIDEBAR_ENTRIES: SidebarEntry[] = [
  // Personalisation
  { id: "general", label: "General", icon: "◈", group: "personalisation" },
  { id: "voice", label: "Voice", icon: "◍", group: "personalisation" },
  { id: "themes", label: "Themes", icon: "◐", group: "personalisation" },
  { id: "memory", label: "User Memory", icon: "▣", group: "personalisation" },
  // System
  { id: "security", label: "Security", icon: "⛨", group: "system" },
  { id: "mac", label: "Mac Control", icon: "⚙", group: "system" },
  { id: "secrets", label: "Secrets", icon: "⚿", group: "system" },
  { id: "channels", label: "Channels", icon: "◉", group: "system" },
];
```

**Edit 2: Update `SettingsSidebar.tsx` to import from constants** (~−15 LoC net — replaces inline SIDEBAR_ENTRIES).

**New component: `frontend/src/components/layout/SettingsDrawer.tsx`** (~140 LoC):

```tsx
import { SIDEBAR_ENTRIES, type SettingsTab } from "../../routes/settings/constants";

interface SettingsDrawerProps {
  open: boolean;
  onClose: () => void;
  onSelect: (tab: SettingsTab) => void;
  activeTab: SettingsTab;
}

export function SettingsDrawer({ open, onClose, onSelect, activeTab }: SettingsDrawerProps) {
  // Escape key handler
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  // Body scroll lock while open
  useEffect(() => {
    if (open) {
      const original = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => { document.body.style.overflow = original; };
    }
  }, [open]);

  if (!open) return null;

  return (
    <div role="dialog" aria-modal="true" aria-label="Settings sections"
         className="fixed inset-0 z-50 flex items-end">
      <div className="absolute inset-0 bg-black/40 animate-fade-in" onClick={onClose} aria-hidden="true" />
      <div className="relative w-full bg-bg-card rounded-t-2xl h-[80vh] flex flex-col animate-slide-up
                      safe-bottom shadow-2xl">
        <div className="flex justify-center pt-2 pb-1" aria-hidden="true">
          <div className="w-12 h-1.5 bg-muted rounded-full" />
        </div>
        <div className="flex items-center justify-between px-4 pb-2">
          <h2 className="font-mono text-lg">Settings</h2>
          <button onClick={onClose} aria-label="Close settings drawer"
                  className="w-10 h-10 flex items-center justify-center rounded-full hover:bg-bg-elevated">
            ✕
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          {(["personalisation", "system"] as const).map(group => (
            <div key={group} className="mb-4">
              <h3 className="text-xs uppercase tracking-wide text-muted mb-2">
                {group === "personalisation" ? "Personalisation" : "System"}
              </h3>
              <div className="grid grid-cols-2 gap-2">
                {SIDEBAR_ENTRIES.filter(e => e.group === group).map(entry => (
                  <button key={entry.id} onClick={() => onSelect(entry.id)}
                          aria-current={activeTab === entry.id ? "true" : undefined}
                          className="h-16 px-3 flex items-center gap-2 rounded-lg bg-bg-elevated
                                     hover:bg-bg-overlay focus:bg-bg-overlay
                                     data-[active=true]:border-l-4 data-[active=true]:border-accent">
                    <span className="text-2xl" aria-hidden="true">{entry.icon}</span>
                    <span className="font-mono text-sm">{entry.label}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

CSS for animations (in `gundam.css`, ~10 LoC):
```css
@keyframes slide-up { from { transform: translateY(100%); } to { transform: translateY(0); } }
.animate-slide-up { animation: slide-up 0.2s ease-out; }
@keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
.animate-fade-in { animation: fade-in 0.2s ease-out; }
```

**Edit 3: Update `MobileLayout.tsx`** (~40 LoC):

```tsx
import { useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router";
import { SettingsDrawer } from "./SettingsDrawer";
import { isValidSettingsTab, type SettingsTab } from "../../routes/settings/constants";

export function MobileLayout() {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();

  const tabFromUrl = searchParams.get("tab");
  const activeTab: SettingsTab = (isValidSettingsTab(tabFromUrl) ? tabFromUrl : "general") as SettingsTab;

  const handleSelect = (tab: SettingsTab) => {
    setDrawerOpen(false);
    if (location.pathname === "/settings") {
      navigate(`/settings?tab=${tab}`, { replace: true });
    } else {
      navigate(`/settings?tab=${tab}`);
    }
  };

  // Auto-close drawer on route change
  useEffect(() => {
    return () => setDrawerOpen(false);
  }, [location.pathname]);

  return (
    <>
      {/* ... existing MobileLayout UI ... */}
      <SettingsDrawer open={drawerOpen}
                      onClose={() => setDrawerOpen(false)}
                      onSelect={handleSelect}
                      activeTab={activeTab} />
    </>
  );
}
```

Note: `isValidSettingsTab` should be exported from `constants.ts` so both MobileLayout and settings/index.tsx use the same validator.

The bottom-nav "Settings" button changes from `<Link to="/settings">` to `<button onClick={() => setDrawerOpen(true)}>`. The ⚙ icon link in the header (per survey, currently `<Link to="/settings">`) is also converted.

### Tests

**`frontend/src/components/layout/SettingsDrawer.test.tsx` (NEW, ~100 LoC, 4 tests)**:
1. Renders nothing when `open={false}`
2. Renders 8 tabs in 2 groups when `open={true}`
3. Backdrop click calls `onClose`
4. Escape key calls `onClose`
5. Tab click calls `onSelect(tab)` + `onClose()`

**`frontend/src/components/layout/MobileLayout.test.tsx` (NEW, ~80 LoC, 3 tests)**:
6. Bottom-nav Settings click opens drawer (not navigate)
7. Drawer selection navigates to `/settings?tab=X`
8. Drawer auto-closes on route change

### Files touched
- `frontend/src/routes/settings/constants.ts` (~25 LoC — SIDEBAR_ENTRIES + isValidSettingsTab)
- `frontend/src/routes/settings/SettingsSidebar.tsx` (~−10 LoC — import SIDEBAR_ENTRIES)
- `frontend/src/components/layout/SettingsDrawer.tsx` (NEW, ~140 LoC)
- `frontend/src/components/layout/SettingsDrawer.test.tsx` (NEW, ~100 LoC, 4 tests)
- `frontend/src/components/layout/MobileLayout.tsx` (~40 LoC — drawer state + mount)
- `frontend/src/components/layout/MobileLayout.test.tsx` (NEW, ~80 LoC, 3 tests)
- `frontend/src/styles/gundam.css` (~10 LoC — slide-up + fade-in keyframes)

**Subtotal: ~385 LoC, 7 new tests**

---

## 5. Feature 3: Theme accent picker

### Design decision: global override

One `accent` color overrides all 8 theme presets. Stored in `localStorage["gundam-halo-theme-accent"]`. **Resolution: hex `#rrggbb`** or `null` (no override).

### Critical fix from audit: hover-preview interaction

The original spec was mechanically impossible — inline `style.setProperty("--accent", hex)` on `<html>` always wins CSS cascade, so hover-preview can never show theme defaults.

**Fix**: theme accent is applied via `[data-custom-accent]` attribute selector, not inline style. The CSS cascade works as follows:

```css
/* Theme presets (unchanged): */
[data-theme="gundam-ntd"] { --accent: #00D4FF; }
[data-theme="gundam-unicorn"] { --accent: #FF00FF; }
/* ... 8 themes ... */

/* Custom accent override (NEW): */
[data-custom-accent] { --accent: var(--custom-accent); }
```

Store sets `<html style="--custom-accent: #ff00aa" data-custom-accent="">` instead of `style="--accent: #ff00aa"`. This way:
- Theme preset `--accent` cascades normally (used in `var(--accent)` consumers)
- When `[data-custom-accent]` is present, the override kicks in via the CSS var indirection

**Hover-preview interaction**: ThemeHoverCard's hover-preview sets `data-theme="gundam-ntd"` on `<html>`. The CSS cascade then evaluates:
- `[data-theme="gundam-ntd"] { --accent: #00D4FF }` → theme accent
- `[data-custom-accent] { --accent: var(--custom-accent) }` → custom accent

CSS cascade is order-of-declaration based. **If `[data-custom-accent]` rule comes AFTER theme rules in `gundam.css`, custom wins; if before, theme wins.** Spec mandates custom-accent rule is declared LAST in `gundam.css` to ensure override.

This means hover-preview will still show the custom accent, NOT theme defaults. **Spec corrects the original UX claim**: "Hovering a theme swatch shows the current state (which may be custom accent); on leave, custom accent is re-applied (idempotent — no visual change)." The hover-preview's value is purely for showing the hover affordance, not for showing theme defaults to override custom accent.

If user wants to "preview" a different theme's accent, they should commit (click) the theme first.

### UI spec

**Edit 1: `frontend/src/routes/settings/ThemesTab.tsx`** (~70 LoC):

Add an "Accent color" sub-section below the existing theme picker (audit correction: ThemesTab does NOT currently have a live-preview block):

```tsx
function AccentPicker() {
  const accent = useThemeStore((s) => s.accent);
  const setAccent = useThemeStore((s) => s.setAccent);

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <label htmlFor="accent-input" className="text-sm font-mono">Custom accent</label>
        <input id="accent-input"
               type="color"
               value={accent || "#00D4FF"}
               onChange={(e) => setAccent(e.target.value)}
               aria-describedby="accent-help"
               className="w-10 h-10 rounded cursor-pointer" />
        <span className="font-mono text-xs text-muted">{accent || "(theme default)"}</span>
        <button onClick={() => setAccent(null)}
                disabled={accent === null}
                aria-label="Reset accent to theme default"
                className="px-3 py-1 text-xs font-mono rounded border disabled:opacity-50">
          Reset
        </button>
      </div>
      <p id="accent-help" className="text-[10px] text-muted">
        Overrides --accent across all themes. Click Reset to restore the active theme's preset.
      </p>
    </div>
  );
}
```

Wire `<AccentPicker />` into ThemesTab after the existing theme picker block.

**Edit 2: `frontend/src/stores/theme.ts`** (~30 LoC, follows existing init pattern from lines 41/70 — NOT onRehydrateStorage):

```ts
// Add to store state interface:
accent: string | null;

// Add to localStorage init (alongside existing lines 41, 70):
const storedAccent = (() => {
  const v = localStorage.getItem("gundam-halo-theme-accent");
  return v && /^#[0-9a-f]{6}$/i.test(v) ? v : null;
})();

// New actions:
setAccent: (hex: string | null) => {
  const validated = hex && /^#[0-9a-f]{6}$/i.test(hex) ? hex : null;
  if (validated === null && hex !== null) return; // invalid input silently rejected
  set({ accent: validated });
  applyAccentToDom(validated);
  if (validated) {
    localStorage.setItem("gundam-halo-theme-accent", validated);
  } else {
    localStorage.removeItem("gundam-halo-theme-accent");
  }
};

// DOM helper (module-level, not exported):
function applyAccentToDom(hex: string | null) {
  if (hex) {
    document.documentElement.style.setProperty("--custom-accent", hex);
    document.documentElement.setAttribute("data-custom-accent", "");
  } else {
    document.documentElement.style.removeProperty("--custom-accent");
    document.documentElement.removeAttribute("data-custom-accent");
  }
}

// On store init, apply persisted accent:
if (storedAccent) applyAccentToDom(storedAccent);
```

**Edit 3: `frontend/src/styles/gundam.css`** (1 LoC — declare custom-accent rule AFTER all theme rules):

```css
/* All theme [data-theme="..."] { --accent: ... } rules FIRST (existing) */
/* ... */

/* Custom accent override (MUST be last): */
[data-custom-accent] { --accent: var(--custom-accent); }
```

### Tests

**`frontend/src/stores/theme.test.ts` (NEW, ~80 LoC, 5 tests)**:
1. Default `accent` is `null`
2. `setAccent("#00ffaa")` updates state + sets `data-custom-accent` + `--custom-accent`
3. `setAccent(null)` removes both attribute and inline style
4. `setAccent("invalid")` silently rejected, state unchanged
5. localStorage round-trip persists accent across store rehydration

**`frontend/src/routes/settings/ThemesTab.test.tsx` (NEW, ~80 LoC, 2 tests)**:
6. Renders color input + reset button
7. Reset button is disabled when `accent === null`

### Files touched
- `frontend/src/routes/settings/ThemesTab.tsx` (~70 LoC — accent picker UI)
- `frontend/src/routes/settings/ThemesTab.test.tsx` (NEW, ~80 LoC, 2 tests)
- `frontend/src/stores/theme.ts` (~30 LoC — accent state + setter + DOM helper)
- `frontend/src/stores/theme.test.ts` (NEW, ~80 LoC, 5 tests)
- `frontend/src/styles/gundam.css` (~1 LoC — `[data-custom-accent]` rule last)

**Subtotal: ~261 LoC, 7 new tests**

---

## 6. Documentation

### `docs/FEATURE-SPEC-SPRINT51-SETTINGS-SEARCH-MOBILE-ACCENT.md`
This file.

### `docs/DASHBOARD.md` updates
- §3.5 (Mobile Layout) — add "Settings drawer" section
- §4.5 (Settings) — add ⌘K search section + accent picker section
- §4.7 (Themes) — document `--custom-accent` CSS var override

### `docs/CHANGELOG.md` [Unreleased]
3 entries under Sprint 51:
- ⌘K settings search (CommandPalette Settings category + button)
- Mobile settings drawer (SettingsDrawer bottom-sheet + auto-close on route change)
- Theme accent picker (global override via `--custom-accent` + data-custom-accent attribute)

### Profile memory update (post-ship)
- Update "Gundam Halo control surface priority" if accent picker affects any priority decision — likely no impact.
- Add: "Gundam Halo — settings page ⌘K search + mobile drawer + accent picker (2026-07-01) — Sprint 51 shipped. Custom accent uses `--custom-accent` CSS var with `[data-custom-accent]` selector declared AFTER theme rules."

---

## 7. Versioning

`__version__`: `0.1.22` → `0.1.23` (MINOR — 3 user-facing capabilities)

4 surfaces to sync per profile memory:
- `backend/app/__init__.py`: `__version__ = "0.1.23"`
- `frontend/package.json`: `"version": "0.1.23"`
- `frontend/src-tauri/Cargo.toml`: `version = "0.1.23"`
- `frontend/src-tauri/tauri.conf.json`: `"version": "0.1.23"`

---

## 8. Test plan

### Backend
No backend changes. **0 new tests.** Existing 1367 must remain green.

### Frontend
| File | New tests | Coverage |
|---|---|---|
| `CommandPalette.test.tsx` (NEW) | 4 | Settings category, deep-link, category filter, escape |
| `routes/settings/index.test.tsx` (NEW) | 4 | ⌘K button, ?tab= sync, sidebar→URL, invalid tab |
| `SettingsDrawer.test.tsx` (NEW) | 4 | Render, backdrop close, tab select, escape |
| `MobileLayout.test.tsx` (NEW) | 3 | Drawer opens on Settings tap, selection navigates, auto-close |
| `theme.test.ts` (NEW) | 5 | Default, setAccent, reset, validation, persistence |
| `ThemesTab.test.tsx` (NEW) | 2 | Color input + reset button |
| **Total** | **22** | |

**Target**: all tests pass, frontend `vitest --run` reports ~140 tests (was ~118 + 22), 0 fail, 0 new TS errors.

### Manual verification
- [ ] Press Cmd+K anywhere → palette opens with previous/all categories (no regression)
- [ ] Press Cmd+K from /settings page header button → palette opens with "Settings" tab pre-selected
- [ ] Select a settings command → navigates to `/settings?tab=X` and the X tab content is rendered
- [ ] Manually visit `/settings?tab=themes` → themes tab active
- [ ] On mobile (Chrome DevTools iPhone 12 emulator), tap bottom-nav Settings → drawer slides up
- [ ] Tap a tab in drawer → navigate to that tab; drawer closes
- [ ] Tap back / navigate away while drawer is open → drawer auto-closes
- [ ] On Themes tab, change accent color → all `--accent` elements update immediately
- [ ] Refresh page → custom accent persists
- [ ] Click "Reset" → custom accent cleared, theme preset accent returns
- [ ] Reset button is greyed out when no custom accent is set

---

## 9. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| CommandPalette category filter breaks existing recents | Low | Low | Recents are stored by command id, not category; unaffected |
| SettingsDrawer backdrop intercepts scroll on iOS Safari | Medium | Medium | `body.style.overflow = "hidden"` while open (spec mitigation); restore on close |
| Custom accent collides with high-contrast accessibility presets | Low | Medium | Reject pure-black `#000000` and pure-white `#ffffff` in validator (presets use these for accent-secondary); document in CHANGELOG |
| `useSearchParams` in settings/index.tsx conflicts with sidebar's onChange | Low | Low | Sidebar's onChange now calls `handleSetActiveTab` which updates both state and URL |
| `[data-custom-accent]` rule ordering matters in `gundam.css` | Low | High | Comment in CSS file mandates "declare AFTER all theme rules"; visual test in /styleguide (Sprint 52) verifies ordering |
| `isValidSettingsTab` validator duplication | Low | Low | Single export in `routes/settings/constants.ts`; both consumers import from there |
| MobileLayout + CockpitLayout switch loses drawer state | Medium | Low | Acceptable: drawer vanishes on desktop; user sees CockpitLayout. Document in DASHBOARD §3.5 |

---

## 10. Out-of-scope reminders

- Storybook-style component gallery → **Sprint 52**.
- Live2D hydration → **Sprint 53**.
- Per-theme accent override (separate from global) → defer to user feedback after Sprint 51 ships.
- ⌘K search in tab content (VoiceTab filter, MemoryTab filter) → defer to Sprint 51.x if users ask.
- Avatar mode preference (Sprint 53 will use `initialMode` in AvatarCard) → defer to Sprint 53.

---

## 11. Done definition

Sprint 51 is **done** when:
1. ⌘K from /settings page button shows only the 8 settings tabs; selecting one navigates to `/settings?tab=X` AND the X tab content renders (URL sync works).
2. Cmd+K globally opens palette without category filter (no regression on existing behavior).
3. On mobile (<768px), tapping Settings in bottom-nav opens a bottom-sheet drawer with the same 8 tabs in 2 groups; selecting navigates and closes the drawer; drawer auto-closes on route change.
4. On the Themes tab, a "Custom accent" color picker sets `--custom-accent` and `data-custom-accent` attribute on `<html>`; persists across reloads; Reset restores theme default.
5. `[data-custom-accent]` CSS rule is the LAST accent-related rule in `gundam.css` (custom wins over theme presets).
6. `__version__` bumped to `0.1.23` across all 4 surfaces.
7. CHANGELOG, DASHBOARD §3.5, DASHBOARD §4.5, DASHBOARD §4.7 updated.
8. Backend 1367 tests pass; frontend vitest ~140 tests pass; tsc 0 errors.
9. Manual smoke through all 3 features in dev build.
10. Commit on gundam-halo main branch.
# Sprint 50 — Theme switcher hover-preview + Settings sidebar nav

**Date**: 2026-07-01
**Status**: Draft
**Author**: Mavis
**Priority**: Medium (UI polish — no functional change; review items #7 + #9 from the 2026-07-01 UI review)
**Depends on**: Sprint 36 (8 themes + theme CSS variables); Sprint 39 (settings page)

## Goal

Two scoped items from the 2026-07-01 UI review, in one sprint
because both are pure presentation-layer changes with the
same low risk profile:

1. **Theme switcher hover-preview** — replace the current
   "click → see name" dropdown with a hover-to-preview grid.
   User moves mouse over a theme swatch → entire cockpit updates
   live (visually) until they leave. Click to commit.
2. **Settings sidebar nav** — replace the 8-tab horizontal bar
   with a vertical sidebar (left rail). Frees horizontal space,
   handles the tab overflow that today barely shows "Security".

No backend changes. No Rust changes. Total ~600 LoC across
~6 files. Test surface: 12 new frontend tests.

## Why now

- The UI review flagged both items explicitly as polish to do
  "Sprint 50+".
- The theme preview is a low-effort UX win — the cockpit already
  re-renders instantly when the theme CSS variable changes
  (Sprint 16 + 36), so the preview loop is just a controlled
  write to `document.documentElement.dataset.theme` with no
  state-side-effects (no toast / no persistence / no race with
  the user-committed value).
- The settings sidebar de-clutters a screen that's currently
  visually crowded (`Security` and `Voice` tabs barely fit at
  1200px viewport).

## Design

### Part 1 — Theme hover-preview

#### Current behaviour

`ThemeSwitcher` is a floating 72×72px circular button (bottom-right)
that opens a dropdown listing 8 themes by emoji + name. Click
an entry → commit (persists to `localStorage["gundam-halo-theme"]`,
re-renders). No preview before commit.

#### New behaviour

Hover-to-preview grid + click-to-commit. Lives in a `HoverCard`
(Radix-style — already in `components/ui/`? if not, use a
positioned `div` with `onMouseEnter` / `onMouseLeave`).

Layout:

```
┌──────────────────────────────────────────────────────────────┐
│ 🎮 MS MODE  ←[floating 56×56 button, shrunk]                │
└──────────────────────────────────────────────────────────────┘
                                  │ hover
                                  ▼
                  ┌───────────────────────────────────┐
                  │ PREVIEW: NT-D        [× close]   │
                  │ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │
                  │ │ 🦄  │ │ ⚡  │ │ 💀  │ │ 🌿  │   │
                  │ │ NT-D│ │SEED │ │CROSS│ │GREEN │   │
                  │ └─────┘ └─────┘ └─────┘ └─────┘   │
                  │ ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐   │
                  │ │ 🌐  │ │ ⚔  │ │ 🔥  │ │ ✨  │   │
                  │ │ 00  │ │DESTY│ │ GOD │ │KAWAI│   │
                  │ └─────┘ └─────┘ └─────┘ └─────┘   │
                  │                                   │
                  │ [✓ Commit (NT-D)]  [✗ Reset]      │
                  └───────────────────────────────────┘
```

#### State machine

```
THEME_PREVIEW_STATE = {
  committed: string | null,  // persisted (localStorage)
  hovering: string | null,    // live preview (NOT persisted)
}
```

- `committed` = what `localStorage` says + what `useThemeStore`
  reports. Updates on commit (click) or reset.
- `hovering` = what `document.documentElement.dataset.theme`
  is currently set to. Updates on `onMouseEnter` of a swatch;
  resets to `committed` on `onMouseLeave` of the entire card
  OR on Escape key OR on click outside.
- The cockpit's CSS reads `[data-theme]` — we mutate the DOM
  attribute directly (no React re-render needed → 60 FPS preview).
- The current committed theme is shown with a cyan border ring
  on its swatch.

#### Hover-card layout (2 rows × 4 cols)

Each swatch = 80×80px box:
- Emoji (32px) on top
- Theme name (uppercase Rajdhani, 11px) below
- The committed theme's swatch: cyan border + glow
- Hovered swatch: bg-elevated background

Card frame: corner brackets (matches `HudCard` style) +
background blur.

#### Behavior details

- **Hover delay**: 100 ms before applying preview (prevents
  flicker on cursor pass-through).
- **Leave**: 200 ms before reverting to committed (gives the user
  time to move from one swatch to another without flicker).
- **Click**: commits `hovering` as the new `committed`. Card
  closes. Toast: "Theme: NT-D".
- **Reset**: button to revert to `null` (= theme follows system).
  Toast: "Theme: System default".
- **Keyboard**: arrow keys navigate the grid; Enter commits;
  Escape closes.
- **Persistence**: committed → `localStorage["gundam-halo-theme"]`
  (already wired). Hovering → NOT persisted (intentional).

#### Reuse `THEMES` constant

`THEMES` (lines 13-22) already has the 9 entries. We just iterate
the same array — no new theme metadata needed. Add one new
field `swatch: string` per entry (CSS colour or emoji already
covers this) — actually emoji is the swatch, we don't need a
separate field. Just iterate.

### Part 2 — Settings sidebar nav

#### Current behaviour

Horizontal 8-tab bar (Sprint 36). Each tab is `min-w-[120px]`
+ flex-1, so 8 × 120 = 960px minimum. At 1280px viewport the
bar fits but the labels are tight. At ≤1024px (iPad portrait,
split-screen iPhone 12) the bar overflows and scrolls
horizontally — users have to swipe right to see "Security".

#### New behaviour

Vertical sidebar nav (left rail). 240px wide. Group tabs into
2 sections:

```
┌─ Personalisation ────────┐
│ ◈ General                │   ← active = cyan border-left
│ ◍ Voice                  │
│ ◐ Themes                 │
│ ▣ User Memory            │
├─ System ─────────────────┤
│ ⛨ Security               │
│ ⚙ Mac Control            │
│ ⚿ Secrets                │
│ ◉ Channels               │
└──────────────────────────┘
   [Main content area — wider because sidebar eats 240px]
```

Visual style:
- 1px left border on active tab (3px cyan).
- Section dividers: subtle 1px horizontal line with section
  label (uppercase Rajdhani, 10px, text-muted).
- Hover: bg-elevated background + left border 1px text-muted.
- Mobile (≤768px): collapse sidebar into a horizontal
  bottom-sheet with the same grouping. Triggered via existing
  `useResponsive()` hook.

#### Sidebar component

New `SettingsSidebar.tsx` (~120 LoC):
- Props: `active: SettingsTab`, `onChange: (tab) => void`,
  `collapsed: boolean`, `onToggleCollapse`.
- Internally: 2 sections (Personalisation / System) with the
  8 tabs split per the diagram above.
- Local-storage persistence: `localStorage["gundam-halo-settings-sidebar-collapsed"]`
  = "true" collapses to a 48px-wide icon-only rail.

#### Content area sizing

Today the content area is full-width (max-w-7xl or similar).
After the sidebar, content area shrinks by 240px (sidebar) +
16px (gap). On a 1280px viewport the content area goes from
~1024px to ~768px — still plenty for most form fields, and
the existing `space-y-3` cards stack gracefully.

#### Keyboard nav

- `j` / `k` (or arrow keys): move down/up the tab list.
- `Enter`: activate the highlighted tab.
- `1-8`: jump directly to the Nth tab (1-indexed; numbered
  next to each tab label).
- `g` then `s`: jump to "Security" (Vim-style mnemonics;
  defer to Sprint 51 if too much work).

#### Mobile sidebar

For `<768px` viewports:
- Sidebar collapses to a bottom-sheet drawer (slides up from
  bottom; 80vh tall).
- Triggered by a floating "⚙ Settings" button (similar to the
  current `ThemeSwitcher` floating button).
- Tabs laid out as 2×4 grid of large touch targets.

This is a stretch goal — Sprint 50 ships desktop sidebar first.
If the mobile drawer doesn't fit cleanly, defer to Sprint 51.

## Files to create / modify

### Frontend (~600 LoC)

- `frontend/src/components/gundam/ThemeSwitcher.tsx` — replace
  dropdown with `HoverPreviewCard` (~120 LoC refactor).
- `frontend/src/components/gundam/ThemeHoverCard.tsx` NEW
  (~180 LoC) — the hover-preview card with state machine +
  delay logic + keyboard nav.
- `frontend/src/components/gundam/HoverPreviewSwatch.tsx` NEW
  (~40 LoC) — single swatch component (extracts the inline
  styling).
- `frontend/src/routes/settings/SettingsSidebar.tsx` NEW
  (~140 LoC) — vertical sidebar with grouping + collapse +
  keyboard nav + mobile drawer.
- `frontend/src/routes/settings/index.tsx` — replace horizontal
  tab bar with `SettingsSidebar` (~30 LoC diff).
- `frontend/src/stores/theme.ts` — add `hoverTheme` field +
  setter (currently only has `theme` / `setTheme`).

### Docs (~80 LoC)
- `docs/FEATURE-SPEC-SPRINT50-THEME-SIDEBAR.md` (this file).
- `docs/CHANGELOG.md` [Unreleased] entry.
- `docs/DASHBOARD.md` — update Settings tab description (visual
  change).

### Tests (~12 new tests)
- `frontend/src/components/gundam/ThemeHoverCard.test.tsx`
  NEW (~120 LoC, 5 tests):
  - `test_hovering_swatch_updates_document_data_theme` (mock
    `useState` for `hoverTheme`; verify `document.documentElement.dataset.theme`
    is set to the hovered theme after delay).
  - `test_leaving_card_reverts_to_committed_after_delay`.
  - `test_clicking_swatch_commits_and_toasts`.
  - `test_escape_key_closes_card_without_committing`.
  - `test_committed_swatch_has_cyan_border_class`.
- `frontend/src/routes/settings/SettingsSidebar.test.tsx` NEW
  (~100 LoC, 4 tests):
  - `test_renders_8_tabs_in_2_groups_personalisation_and_system`.
  - `test_clicking_tab_calls_onChange_with_correct_id`.
  - `test_active_tab_has_left_border_highlight`.
  - `test_collapse_toggle_persists_to_localStorage`.
- `frontend/src/components/gundam/ThemeSwitcher.test.tsx` NEW
  (~80 LoC, 3 tests):
  - `test_button_aria_label_mentions_preview`.
  - `test_hover_over_button_opens_hover_card`.
  - `test_committed_theme_reflected_in_button_subtitle` (e.g.
    the floating button shows "🎮 NT-D" when NT-D is committed,
    not the generic "MS MODE" string).

## Acceptance criteria

- [ ] Hover over any swatch in the new ThemeSwitcher card
  updates `document.documentElement.dataset.theme` within 100ms.
- [ ] Mouse leaves the card → reverts to committed theme
  within 200ms (no flicker, no animation glitch).
- [ ] Click a swatch → commits; toast: "Theme: NT-D".
- [ ] Escape closes the card without committing.
- [ ] `/settings` shows vertical sidebar; "Security" tab is
  fully visible at 1024px viewport (currently overflows).
- [ ] Active tab has 3px cyan left border.
- [ ] Sidebar collapse state persists across reload.
- [ ] Mobile (≤768px) shows bottom-sheet drawer with 2×4 grid.
- [ ] All 12 new vitest tests pass.
- [ ] Backend tests untouched (1367 stays).
- [ ] `cargo check --tests` clean.

## Version bump

`__version__` 0.1.21 → **0.1.22** (PATCH per Mavis memory rule —
presentation polish, no new functional capability). 4 surfaces
synced.

## Out of scope (deferred to future sprints)

- **Theme accent-color picker** (custom accent beyond the 8
  presets). Sprint 51+.
- **Per-theme font overrides** (NT-D uses Rajdhani; KAWAII could
  use a chibi-friendly font). Sprint 52+.
- **Settings sidebar search** (`⌘K` to fuzzy-find any tab).
  Sprint 51.
- **Vim-style mnemonics** (`g s` for Security). Sprint 51 if
  scope fits.
- **Settings tab keyboard shortcuts** (`1`-`8` jump to Nth
  tab). Sprint 51 — Sprint 50 keeps it to j/k/Enter.
- **Mobile sidebar drawer polish** (gesture support, drag-to-close).
  Sprint 51.
- **Theme-preview persistence mode** (option to "remember preview
  as committed" with a 5s delay so users don't lose their
  experiment). Out — current "click to commit" is simpler.

## Why this is the right minimal surface

- Pure presentation; zero backend / Rust changes.
- Both items are 1-2 day items; combined = 3-4 days = 1 sprint.
- Both are explicit "Sprint 50+" entries from the review — doing
  them now closes the open polish items before they pile up.
- Theme preview is a real UX win (try a theme without committing
  is a 30-second decision; commit-then-revert is a 60-second
  decision; the cumulative cost across 8 themes × multiple
  contexts is meaningful).
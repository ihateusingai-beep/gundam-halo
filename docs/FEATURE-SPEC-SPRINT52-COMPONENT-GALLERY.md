# FEATURE-SPEC — Sprint 52: Component Gallery + Orphaned Component Audit

**Sprint owner:** Mavis
**Target version:** `0.1.23` (PATCH, ships together with Sprint 51)
**Prereqs:** Sprint 50 ✅ shipped (HudCard is the canonical container)
**Estimated LoC:** ~750-850 LoC, 7-9 new tests (revised up after audit)

> **Revision note**: 2026-07-01 audit found count discrepancies + audit script gaps. This revision corrects component counts and adds the JSDoc-skip filter to `audit-orphans.ts`. Component deletions themselves remain the same (4 orphans verified, 1 kept for Sprint 53).

---

## 1. Goal & non-goals

### Goal

Two parallel concerns:

1. **Component gallery (`/styleguide` route)** — render every wired React component in isolation, with its JSDoc surfaced as docs and a state-controls panel. Gives the team (and user) a one-stop visual catalogue of every UI building block. Lives in the same Vite app — no separate dev server, no ~400MB of Storybook deps.
2. **Orphaned component audit** — list, verify, and remove dead components. The 2026-07-01 audit verified **5 components** are unused or unused-when-imported:

| File | LoC | Status |
|---|---|---|
| `components/gundam/EnergyBar.tsx` | 29 | Fully orphan — DELETE |
| `components/gundam/HoloPanel.tsx` | 48 | Fully orphan — DELETE |
| `components/gundam/RingProgress.tsx` | 89 | Fully orphan — DELETE |
| `components/gundam/GundamAvatar.tsx` | 104 | Fully orphan — DELETE |
| `components/live2d/Live2DCanvas.tsx` | 48 | Imported but unused — KEEP for Sprint 53 |

### Non-goals

- Real Storybook installation (~400MB deps). Rejected.
- Auto-generated prop tables (defer; hand-curated JSDoc excerpts are fine for v1).
- Per-component visual regression screenshots — defer to Sprint 54+.
- "Reverse" orphan audit (rarely-used components) — out of scope.
- Live2DCanvas wiring — **Sprint 53**.

---

## 2. Audit corrections applied (2026-07-01)

| Original claim | Corrected reality |
|---|---|
| `gundam/` has 30 .tsx files | Actual: 36 |
| `wizard/` has 9 .tsx files | Actual: 15 (WizardShell + 8 steps + 6 step.test.tsx; total files 15 if counting tests; 9 source files) |
| Total components = 54 | Actual: 67 (incl. 17 .test.tsx files) |
| 24 .test.tsx companion files | Actual: 17 |
| Wizard total ~1680 LoC | Actual: 1333 LoC |
| `audit-orphans.ts` doesn't filter JSDoc | Now filters lines starting with `*`, `//`, `/*` before grepping |

---

## 3. Feature 1: Component gallery (`/styleguide` route)

### Approach

New route `/styleguide` that renders every wired component inside a `<HudCard>` block. Block has 3 sections:
1. **Header** — component name + file path (link to source) + JSDoc excerpt (first 5-15 lines)
2. **Stage** — the component itself, mounted with default props + a "props" form panel for editing simple props
3. **State controls** — common props editable inline; for components with internal state, a "Reset to default props" button

Renders inside `<CockpitLayout>` so theme/responsive context works.

### UI spec

**Layout** (`frontend/src/routes/styleguide.tsx`, NEW, ~700 LoC):

```tsx
import { Routes, Route } from "react-router";
import { CockpitLayout } from "../components/layout/CockpitLayout";
import { COMPONENT_GROUPS, type ComponentShowcase } from "./styleguide-data";

export function StyleguidePage() {
  return (
    <div className="gundam-cockpit-frame flex-1 p-6 overflow-y-auto">
      <h1 className="gundam-heading mb-2">Component Gallery</h1>
      <p className="text-xs text-muted mb-6">
        {COMPONENT_GROUPS.reduce((n, g) => n + g.components.length, 0)} components · auto-loaded from JSDoc
      </p>

      {COMPONENT_GROUPS.map(group => (
        <section key={group.label} className="mb-8">
          <h2 className="gundam-heading-sm mb-3">{group.label}</h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {group.components.map(comp => (
              <ComponentShowcase key={comp.id} {...comp} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function ComponentShowcase({ name, filePath, docs, mount, defaultProps, editableProps }: ComponentShowcase) {
  const [props, setProps] = useState(defaultProps);

  return (
    <HudCard>
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-mono text-sm">{name}</h3>
        <a href={`vscode://file${filePath}`}
           className="text-xs"
           onClick={(e) => { if (!(window as any).vscode) { e.preventDefault(); alert(`Source: ${filePath}`); } }}>
          📁 {filePath.split('/').pop()}
        </a>
      </div>
      <pre className="text-[10px] text-muted mb-3 whitespace-pre-wrap">{docs}</pre>
      <ErrorBoundary name={name}>
        <div className="bg-bg-elevated p-4 rounded mb-3 flex items-center justify-center min-h-[80px]">
          {mount(props)}
        </div>
      </ErrorBoundary>
      <PropEditor spec={editableProps} value={props} onChange={setProps} />
      <button onClick={() => setProps(defaultProps)}
              className="text-[10px] font-mono underline text-muted mt-2">
        Reset to default props
      </button>
    </HudCard>
  );
}

class ErrorBoundary extends React.Component<{ name: string; children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(error: Error) { console.warn(`[styleguide] ${this.props.name} crashed:`, error); }
  render() {
    if (this.state.error) return <div className="text-xs text-danger p-2">⚠ {this.state.error.message}</div>;
    return this.props.children;
  }
}
```

**Route registration** (`frontend/src/App.tsx`, ~3 LoC):
```tsx
<Route path="/styleguide" element={<StyleguidePage />} />
```

**Data file**: `frontend/src/routes/styleguide-data.ts` (NEW, ~500 LoC):

Contains `COMPONENT_GROUPS: Array<{ label: string; components: ComponentShowcase[] }>` with hand-curated entries for ~55 components across 9 groups. Each entry has:
- `name`: string
- `filePath`: absolute path under `frontend/src/`
- `docs`: JSDoc excerpt (first 5-15 lines, hand-copied from source)
- `mount: (props) => ReactNode`: factory returning the mounted component
- `defaultProps`: object
- `editableProps`: Array<{ key, label, type: "string" | "number" | "boolean", options? }>

### Component catalogue (corrected counts)

| Group | Components | LoC (corrected) |
|---|---|---|
| Layout & shell | HudCard, CockpitLayout chrome, MobileLayout nav | ~580 |
| Status & indicators | BackendHealthBanner, ConnectionStatus, RestartNudgeBanner, StatusDot, VoiceWsIndicator, Gauge | ~550 |
| Themes & preview | ThemeSwitcher, ThemeHoverCard, HoverPreviewSwatch | ~402 |
| Cards & lists | MissionCard, MissionLog, MissionSelect, ProjectCard, SignalCard, Radar | ~615 |
| Chat & conversation | MessageBubble, ToolCallTrace, ToolCallTraceList, CommandInput, WakePhraseHint, VoicePanel chrome, CyberWaveform | ~1100 |
| Wizard & setup | WizardShell + 8 steps | ~1333 |
| Dashboard cards | HeldOutEvalCard, CorpusBreakdownChart, ModelSwapDialog | ~1054 |
| Live2D (preview) | CSSAvatar, ImageSetAvatar (Live2DCanvas skipped — Sprint 53) | ~512 |
| Settings tab previews | 8 tabs as accordion | ~1700 |

**Total: ~7846 LoC across ~55 components**

### Tests

`frontend/src/routes/styleguide.test.tsx` (NEW, ~100 LoC, 4 tests):
1. Renders the gallery header
2. Renders all 9 group sections
3. Each ComponentShowcase mounts without throwing (smoke test for all 55)
4. Reset button restores default props

### Files touched

- `frontend/src/routes/styleguide.tsx` (NEW, ~300 LoC — page + ComponentShowcase + ErrorBoundary)
- `frontend/src/routes/styleguide-data.ts` (NEW, ~500 LoC — COMPONENT_GROUPS catalogue)
- `frontend/src/routes/styleguide.test.tsx` (NEW, ~100 LoC, 4 tests)
- `frontend/src/App.tsx` (~3 LoC — add route)
- `frontend/src/components/layout/CockpitLayout.tsx` (~0 LoC — already mounted)

**Subtotal: ~903 LoC, 4 new tests**

---

## 4. Feature 2: Orphaned component audit + cleanup

### Decision: delete or keep?

| Component | LoC | Decision | Reason |
|---|---|---|---|
| `EnergyBar.tsx` | 29 | **DELETE** | Fully orphan (verified 0 importers); ProjectCard inlines `gundam-energy-bar` CSS class (verified) |
| `HoloPanel.tsx` | 48 | **DELETE** | Fully orphan; superseded by HudCard |
| `RingProgress.tsx` | 89 | **DELETE** | Fully orphan; never wired into /projects/new |
| `GundamAvatar.tsx` | 104 | **DELETE** | Fully orphan; CSSAvatar is a superset |
| `Live2DCanvas.tsx` | 48 | **KEEP** | Sprint 53 will wire it. Just remove the dead import from CockpitLayout. |

### Cleanup actions

**Delete 4 files**:
```bash
mavis-trash \
  frontend/src/components/gundam/EnergyBar.tsx \
  frontend/src/components/gundam/HoloPanel.tsx \
  frontend/src/components/gundam/RingProgress.tsx \
  frontend/src/components/gundam/GundamAvatar.tsx
```

**Edit `frontend/src/components/layout/CockpitLayout.tsx`** (~−2 LoC):
- Remove `import { Live2DCanvas } from "../live2d/Live2DCanvas";` (line 26 — dead import)

**Edit `frontend/src/components/gundam/CyberWaveform.tsx`** (~−1 LoC):
- Line 6 JSDoc: "Multiple CyberWaveform + GundamAvatar instances" → "Multiple CyberWaveform + CSSAvatar instances"

**CSS verification** (must run BEFORE deletion): grep `gundam.css` and `*.css` files for the class names `gundam-energy-bar`, `gundam-holo`, `gundam-ring-progress`, `gundam-avatar` — flag any remaining CSS rules. Spec's risk register acknowledges this; the verification is part of the cleanup flow.

### Audit script

`frontend/scripts/audit-orphans.ts` (NEW, ~70 LoC, with JSDoc-skip filter per audit fix):

```ts
#!/usr/bin/env tsx
// Grep every .tsx file in components/ for its exports,
// then grep the rest of frontend/src for imports of those names
// (skipping JSDoc comment lines and the source file itself).
// Prints "<Name> · <file> · <import_count> imports" with 0 flagged.

import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, basename } from "node:path";
import { execSync } from "node:child_process";

const COMPONENTS_ROOT = "frontend/src/components";
const SEARCH_ROOT = "frontend/src";

interface ExportEntry { name: string; file: string; }

function walk(dir: string): string[] {
  return readdirSync(dir).flatMap(f => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  }).filter(f => f.endsWith(".tsx") && !f.endsWith(".test.tsx") && !f.endsWith(".stories.tsx"));
}

function isCommentLine(line: string): boolean {
  const trimmed = line.trim();
  return trimmed.startsWith("//") || trimmed.startsWith("*") || trimmed.startsWith("/*");
}

function findExports(file: string): ExportEntry[] {
  const src = readFileSync(file, "utf8");
  const lines = src.split("\n");
  const exports: ExportEntry[] = [];
  // Skip the export if it appears inside a JSDoc block
  for (let i = 0; i < lines.length; i++) {
    if (isCommentLine(lines[i])) continue;
    const matches = [...lines[i].matchAll(/export\s+(?:default\s+)?(?:function|const|class)\s+(\w+)/g)];
    for (const m of matches) {
      exports.push({ name: m[1], file });
    }
  }
  return exports;
}

const allExports: ExportEntry[] = [];
for (const file of walk(COMPONENTS_ROOT)) {
  allExports.push(...findExports(file));
}

const offenders: string[] = [];

for (const { name, file } of allExports) {
  // grep -r excluding the source file itself and JSDoc/strings
  try {
    const output = execSync(
      `grep -r "import.*${name}" ${SEARCH_ROOT} --include="*.tsx" --include="*.ts" -l --exclude="${basename(file)}" | xargs grep -L "JSDoc\\|@example" 2>/dev/null | wc -l`
    ).toString().trim();
    const count = parseInt(output);
    if (count === 0) {
      // Double-check: grep with broader pattern (excluding source file)
      const broaderCount = parseInt(execSync(
        `grep -r "${name}" ${SEARCH_ROOT} --include="*.tsx" --include="*.ts" -l --exclude="${basename(file)}" | wc -l`
      ).toString().trim());
      // If only JSDoc/comment hits, the count is 0 but the name appears in docs
      const inComments = parseInt(execSync(
        `grep -r "^\\s*//.*${name}\\|^\\s*\\*.*${name}\\|^\\s*/\\*.*${name}" ${SEARCH_ROOT} --include="*.tsx" --include="*.ts" | wc -l`
      ).toString().trim());
      if (broaderCount === inComments) offenders.push(`${name} · ${file}`);
    }
  } catch (e) {
    // grep returns 1 on no match — treat as 0
    offenders.push(`${name} · ${file}`);
  }
}

console.log(`Found ${offenders.length} orphans:`);
offenders.forEach(o => console.log(`  ${o}`));
process.exit(offenders.length > 0 ? 1 : 0);
```

### Tests

`frontend/scripts/OrphanAudit.test.ts` (NEW, ~50 LoC, 3 tests):
1. After cleanup, no orphan in known list re-appears in `frontend/src/components/gundam/`
2. The 4 deleted files no longer exist
3. `audit-orphans.ts` script runs and exits 0 (post-cleanup)

### Files touched

- 4 file deletions (EnergyBar, HoloPanel, RingProgress, GundamAvatar)
- `frontend/src/components/layout/CockpitLayout.tsx` (~−2 LoC — remove dead import)
- `frontend/src/components/gundam/CyberWaveform.tsx` (~−1 LoC — JSDoc update)
- `frontend/scripts/audit-orphans.ts` (NEW, ~70 LoC, JSDoc-skip filter)
- `frontend/scripts/OrphanAudit.test.ts` (NEW, ~50 LoC, 3 tests)
- `package.json` (~3 LoC — `"audit:orphans": "tsx scripts/audit-orphans.ts"` script)

**Subtotal: ~120 LoC net (after deletions), 3 new tests, 4 files removed**

---

## 5. Documentation

### `docs/FEATURE-SPEC-SPRINT52-COMPONENT-GALLERY.md`
This file.

### `docs/DASHBOARD.md` updates
- §6 (Developer tools) — add `/styleguide` route entry
- §7 (Cleanup) — document Sprint 52 orphan removal

### `docs/CHANGELOG.md` [Unreleased]
2 entries under Sprint 52:
- Component gallery (`/styleguide` route with 9 groups, ~55 components, ErrorBoundary per showcase)
- Orphan cleanup (4 dead components removed; `pnpm audit:orphans` script with JSDoc-skip filter)

---

## 6. Versioning

`__version__`: `0.1.22` → `0.1.23` (PATCH, same release as Sprint 51)

4 surfaces to sync per profile memory:
- `backend/app/__init__.py`: `__version__ = "0.1.23"`
- `frontend/package.json`: `"version": "0.1.23"`
- `frontend/src-tauri/Cargo.toml`: `version = "0.1.23"`
- `frontend/src-tauri/tauri.conf.json`: `"version": "0.1.23"`

---

## 7. Test plan

### Backend
No backend changes. **0 new tests.** Existing 1367 must remain green.

### Frontend
| File | New tests | Coverage |
|---|---|---|
| `styleguide.test.tsx` (NEW) | +4 | Header, all 9 groups, mount-no-throw, reset |
| `OrphanAudit.test.ts` (NEW) | +3 | No re-orphan, deleted files gone, script exit 0 |
| **Total** | **+7** | |

**Target**: frontend vitest ~147 tests pass (was ~118 + 22 Sprint 51 + 7 Sprint 52), 0 fail, 0 new TS errors.

### Manual verification
- [ ] Visit `/styleguide` — all 9 groups render
- [ ] Click "📁" link next to a component name — opens VS Code at source file (or shows path alert if no VS Code handler)
- [ ] Change a prop in PropEditor — component re-renders with new value
- [ ] Click "Reset to default props" — restores default
- [ ] Trigger a crash on one showcase (via bad prop) — ErrorBoundary catches + shows error message
- [ ] Run `pnpm audit:orphans` — prints "Found 0 orphans"
- [ ] `pnpm tsc --noEmit` — 0 errors
- [ ] `pnpm vitest --run` — ~147 tests pass

---

## 8. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Some showcase entries crash due to missing context | High | Medium | ErrorBoundary in ComponentShowcase; warning logged to console |
| `/styleguide` adds ~50KB to bundle | Low | Low | Tree-shake won't help (it's a route); accept size; document in CHANGELOG |
| Users find `/styleguide` accidentally | Low | Low | Header says "Component Gallery"; document in DASHBOARD §6 |
| Deleting 4 components breaks some hidden reference (CSS class in stale stylesheet) | Low | Medium | Run grep BEFORE deletion for `gundam-energy-bar`/`gundam-holo`/`gundam-ring-progress`/`gundam-avatar` in all CSS files; remove orphan CSS rules |
| Live2DCanvas.tsx actually IS used somewhere I missed | Low | Low | Survey + audit verified only CockpitLayout imports it; Sprint 53 wires it |
| Audit script flags JSDoc examples as imports (false positive) | Low | Low | JSDoc-skip filter implemented in §4 (line-level filtering + double-check) |
| `tsx` dep not installed (script can't run) | Medium | Low | Add `tsx` to devDependencies if missing |
| ErrorBoundary suppresses real bugs | Medium | Low | Logs warning to console; dev can spot during testing |

---

## 9. Out-of-scope reminders

- Real Storybook installation → explicitly deferred
- Auto-generated prop tables → defer
- Visual regression screenshots → defer to Sprint 54+
- Live2D hydration → **Sprint 53**
- Reverse orphan audit (rarely-used) → defer

---

## 10. Done definition

Sprint 52 is **done** when:
1. `/styleguide` route renders all 9 component groups; each ComponentShowcase mounts its component without throwing; ErrorBoundary catches any crashes.
2. `pnpm audit:orphans` script reports 0 orphans.
3. 4 dead components deleted; `Live2DCanvas.tsx` import removed from CockpitLayout; CSS orphan rules cleaned.
4. `pnpm tsc --noEmit` reports 0 errors.
5. `pnpm vitest --run` reports ~147 tests passing (118 + 22 Sprint 51 + 7 Sprint 52).
6. CHANGELOG, DASHBOARD §6, DASHBOARD §7 updated.
7. Sprints 51 + 52 commit on gundam-halo main as single `0.1.23` release.
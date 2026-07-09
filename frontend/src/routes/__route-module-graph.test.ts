/**
 * Route module-graph smoke test.
 *
 * Guards against the **Sprint 56 R3 class of bug**: when a
 * route component is renamed / moved (e.g. `git mv` from one
 * folder to another), a wrong relative-import path in any
 * transitively-imported file can survive a commit cycle
 * because neither Vite nor `tsc --noEmit` exercises the
 * runtime module graph at PR time.
 *
 * ## How this test catches it
 *
 * `import.meta.glob` with a `./<glob>` relative to this
 * file's directory makes
 * Vite transform-time-resolve every matching file's static
 * import graph. Any `from "./missing"` or `from "@/components/
 * gone"` surfaces as a `Failed to resolve import` error in
 * the smoke test's transform step — at PR-time, in CI, before
 * the user navigates.
 *
 * ## Caveats (a Playwright layer would cover these but costs more)
 *
 *  - Runtime JSX errors inside a tab only render when the
 *    SettingsPage is mounted (we don't simulate that here).
 *  - React.lazy() fallback failures (we don't use React.lazy
 *    today).
 *  - CSS / Tailwind missing-class (vitest has `css: false`).
 * But for the "wrong import path after a refactor" class of
 * bug, this test catches it.
 *
 * ## Filename: `__route-module-graph.test.ts`
 *
 * The `__` prefix is **load-bearing** for two reasons:
 *
 *  1. The `import.meta.glob` call below resolves
 *     relative to **this file's directory** (`src/routes/`).
 *     Moving this file out of `src/routes/` would break the
 *     relative glob path. Co-locating with route files keeps
 *     the import paths short and obvious.
 *  2. The vitest `include` pattern matches the file AND Vite's
 *     default `include` for the transform pipeline also
 *     matches it. The smoke file must be filterable in the
 *     suite-block test (line ~115) so it doesn't pollute the
 *     "every .tsx file under routes/" assertion. Renaming
 *     requires updating line ~115 too.
 *
 * Don't move this file to `src/__tests__/`. Don't rename it
 * without also updating the filter in the suite-block test.
 */
import { describe, expect, it } from "vitest";

// Eager glob — vitest's loader resolves every matching module
// at transform time, which is what surfaces the broken-import
// class of bug. `{ eager: true }` returns the modules
// synchronously; we then inspect the exports to confirm the
// module exposes a component.
const ROUTE_MODULES = import.meta.glob<Record<string, unknown>>(
  "./**/*.tsx",
  { eager: true },
);

// Route entries are the **exact files App.tsx imports**. We
// list them by relative path AND record what named export
// App.tsx consumes. If you add a route, add it here too —
// the suite-block test at the bottom will fail with a clear
// message about the unindexed file.
//
// IMPORTANT: a "route entry" by this list's definition is
// "a file App.tsx imports as a `Route path=` element".
// Helper files (transitively imported but not directly
// referenced by App.tsx) are NOT entries. See
// `HELPER_PREFIXES` below.
interface RouteEntry {
  file: string;
  /** Named export App.tsx consumes (Route element prop). */
  namedExport: string;
}
const ROUTE_ENTRIES: RouteEntry[] = [
  { file: "./index.tsx", namedExport: "OverviewPage" },
  { file: "./settings.tsx", namedExport: "SettingsPage" },
  { file: "./setup/index.tsx", namedExport: "SetupPage" },
  { file: "./audit.tsx", namedExport: "AuditDashboardPage" },
  { file: "./projects/new.tsx", namedExport: "NewProjectPage" },
  { file: "./projects/[id].tsx", namedExport: "ProjectDetailPage" },
  { file: "./projects/[id]/memory.tsx", namedExport: "ProjectMemoryPage" },
  {
    file: "./projects/[id]/sessions/[sessionId].tsx",
    namedExport: "SessionDetailPage",
  },
  // Sprint 60 R-A3: catch-all 404 page (replaces the pre-existing
  // silent <Navigate to="/" replace />).
  { file: "./NotFound.tsx", namedExport: "NotFoundPage" },
];

// Helper files live next to a route entry but are not
// themselves App.tsx imports. The current convention is:
// every helper file is inside a folder-tree that *originates*
// from a sibling `.tsx` entry. Concretely:
//
//   - `./settings.tsx` (entry) → `./settings/{index,shared,
//     SettingsSidebar}.tsx` and `./settings/tabs/*.tsx` are
//     helpers
//   - `./projects/[id].tsx` (entry) has no helpers (children
//     of `projects/[id]/` are themselves entries because
//     App.tsx imports them directly via the nested route)
//
// Rather than enumerate prefixes by hand, we **infer** helpers
// from "files that descend from an entry's shadow folder". A
// helper is defined recursively:
//
//   helper("./settings/tabs/GeneralTab.tsx") is true iff
//     - `./settings.tsx` is an entry (the shadow root), AND
//     - no ancestor path is itself a folder that has an
//       `index.tsx` entry (which would mean we're now under
//       a nested route, not a helper tree).
//
// Edge cases:
//   - `./settings/SettingsSidebar.tsx` is inferred as a helper
//     because `./settings.tsx` is an entry. ✓
//   - `./projects/new.tsx` is not a helper (lives next to
//     `./projects/[id].tsx` but the directory `./projects/`
//     has no direct entry — both `new.tsx` and `[id].tsx`
//     are themselves entries). ✓
//   - `./settings/tabs/GeneralTab.tsx` is a helper because
//     `./settings.tsx` is an entry, and `./settings/tabs/`
//     has no `index.tsx` entry (so we're not under a nested
//     route). ✓
//
// To declare a NEW helper-tree, register the entry's `.tsx`
// file in ROUTE_ENTRIES (above). All descendants become
// helpers automatically.
function isRouteHelper(relPath: string): boolean {
  // Top-level files (no `/`) are themselves entries or
  // top-level errors. `./settings.tsx` itself is an entry,
  // NOT a helper.
  if (!relPath.includes("/")) return false;
  // Strip the leading "./" and split into parts.
  const parts = relPath.replace(/^\.\//, "").split("/");
  // Walk UP from the file's parent folder toward root,
  // stopping at the **first** registered entry. Two outcomes:
  //
  //   (a) We find a sibling `./<folder>.tsx` entry that is
  //       a SIBLING of the file's IMMEDIATE parent folder —
  //       i.e. `./<folder>.tsx` is at the same directory
  //       depth as the file's first folder. Example:
  //       `./settings/tabs/GeneralTab.tsx` walks UP:
  //         i=3: "./settings/tabs/GeneralTab" — no entry
  //         i=2: "./settings/tabs" — no `./settings/tabs.tsx`
  //         i=1: "./settings" — `./settings.tsx` IS an
  //               entry → return TRUE (helper).
  //   (b) We find `./<folder>/<sub>.tsx` entry that is an
  //       ancestor of the file. Example:
  //       `./projects/[id]/memory.tsx` walks UP:
  //         i=3: "./projects/[id]/memory" — no entry
  //         i=2: "./projects/[id]" — `./projects/[id].tsx`
  //               IS an entry at depth=2, which equals the
  //               file's depth-2 ancestor → return FALSE
  //               (the file is either an entry itself [in
  //               ROUTE_ENTRIES loop above] or a sibling
  //               helper of a nested route, both treated as
  //               "not a route-helper" for our purposes).
  //
  // The asymmetry between (a) and (b) is captured by the
  // index-range check: case (a) shadow is at depth=1 (`i==1`),
  // case (b) shadow is at depth≥2 (`i≥2`). Walk the loop, and
  // when we find the first entry-shadow, decide based on `i`.
  for (let i = parts.length - 1; i >= 1; i--) {
    const folder = parts.slice(0, i).join("/");
    const folderHasIndex = ROUTE_ENTRIES.some(
      (r) => r.file === `./${folder}/index.tsx`,
    );
    const folderHasSibling = ROUTE_ENTRIES.some(
      (r) => r.file === `./${folder}.tsx`,
    );
    if (folderHasIndex || folderHasSibling) {
      // Found the first entry-shadow on the path. If it's an
      // `index.tsx` entry (folderHasIndex) OR a deeper-level
      // sibling (i.e. the file is inside a folder that itself
      // has a route entry), the file is NOT a top-level
      // route-helper. Return false.
      //
      // If it's a depth-1 sibling (`./folder.tsx` AND `i==1`),
      // the file is a helper of that route.
      return i === 1 && folderHasSibling;
    }
  }
  return false;
}

describe("Route module-graph integrity", () => {
  for (const { file, namedExport } of ROUTE_ENTRIES) {
    it(`loads ${file} and exports \`${namedExport}\``, () => {
      const mod = ROUTE_MODULES[file];
      expect(mod, `route file missing from glob: ${file}`).toBeDefined();

      // The named export App.tsx consumes must exist AND be a
      // function (React component shape — function/class/forwardRef).
      const fn = mod[namedExport];
      expect(
        typeof fn === "function",
        `route ${file} does not export a function \`${namedExport}\`. ` +
          `Module keys: ${Object.keys(mod).join(", ")}. ` +
          `If you renamed the export, update ROUTE_ENTRIES.namedExport.`,
      ).toBe(true);
    });
  }

  // Belt-and-suspenders: if anyone added a new `.tsx` under
  // `src/routes/` and forgot to register it here, OR if the
  // helper-inference convention broke, this test fails loudly
  // with a clear list of unindexed files.
  it("every .tsx file under src/routes/ is either a route entry or an inferred helper", () => {
    const indexedFiles = new Set(ROUTE_ENTRIES.map((r) => r.file));
    const allRouteFiles = Object.keys(ROUTE_MODULES)
      .filter((p) => !p.includes("__route-module-graph"))
      .filter((p) => !p.endsWith(".test.tsx"));
    const unindexed = allRouteFiles.filter(
      (f) => !indexedFiles.has(f) && !isRouteHelper(f),
    );
    expect(
      unindexed,
      `Found route files not in ROUTE_ENTRIES and not inferred as helpers:\n` +
        `  ${unindexed.join("\n  ")}\n` +
        `If this is a new helper, add the parent .tsx entry to HELPER_INFERENCE_ROOT.` +
        `\nIf this is a new route entry, add it to ROUTE_ENTRIES.`,
    ).toEqual([]);
    // Also: matched count must equal entry count + helper count.
    // Catches the inverse case (we inferred too many as helpers).
    const inferredHelpers = allRouteFiles.filter(isRouteHelper).length;
    expect(allRouteFiles.length).toBe(ROUTE_ENTRIES.length + inferredHelpers);
  });
});

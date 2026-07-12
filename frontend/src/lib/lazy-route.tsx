import { lazy, type ComponentType, type LazyExoticComponent } from "react";

/**
 * Wrap a named-export component in `React.lazy()` for code-splitting.
 *
 * Sprint 68 X-B1: code-split 783KB initial bundle.
 *
 * ## Why this helper exists
 *
 * `React.lazy()` requires the dynamic import to return a module
 * with a `default` export. Gundam Halo routes use NAMED exports
 * (e.g. `export function AuditDashboardPage() { ... }`) per
 * the route module-graph test convention
 * (`src/routes/__route-module-graph.test.ts` — Sprint 60). Without
 * this helper, every lazy import in `App.tsx` would need:
 *
 * ```tsx
 * const AuditDashboardPage = lazy(() =>
 *   import("@/routes/audit").then((m) => ({
 *     default: m.AuditDashboardPage,
 *   })),
 * );
 * ```
 *
 * The repeated `.then((m) => ({ default: m[exportName] }))` is
 * error-prone (forget the rename → "Element type is invalid").
 * This helper centralises the pattern + adds a runtime check
 * that the named export exists and is a function.
 *
 * ## Usage
 *
 * ```tsx
 * const AuditDashboardPage = lazyRoute(
 *   () => import("@/routes/audit"),
 *   "AuditDashboardPage",
 * );
 *
 * <Route
 *   path="/audit"
 *   element={
 *     <Suspense fallback={<RouteFallback />}>
 *       <AuditDashboardPage />
 *     </Suspense>
 *   }
 * />
 * ```
 *
 * ## Error handling
 *
 * If the named export is missing or isn't a function, the
 * returned lazy component throws when rendered. React's
 * default error boundary catches it. The error message
 * includes the export name + the actual module keys for
 * debugging the mismatch.
 *
 * ## Why not use the default-export dance inline
 *
 * Renaming every route component from named to default export
 * would break the `ROUTE_ENTRIES` named-export contract in
 * `__route-module-graph.test.ts`. The helper is the cheaper
 * path.
 */
export function lazyRoute<P extends object = Record<string, unknown>>(
  importFn: () => Promise<Record<string, unknown>>,
  exportName: string,
): LazyExoticComponent<ComponentType<P>> {
  return lazy(() =>
    importFn().then((mod) => {
      const Component = mod[exportName];
      if (typeof Component !== "function") {
        throw new Error(
          `lazyRoute: export "${exportName}" is missing or not a function. ` +
            `Module keys: ${Object.keys(mod).join(", ")}. ` +
            `If you renamed the export, update the lazyRoute() call.`,
        );
      }
      return { default: Component as ComponentType<P> };
    }),
  );
}

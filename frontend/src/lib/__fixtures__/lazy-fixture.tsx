/**
 * Test fixture for `lazyRoute` — see `lib/lazy-route.test.tsx`.
 *
 * Why a real fixture file (and not a mocked module)?
 *
 * `lazyRoute` calls `import()` at runtime. To exercise the
 * Suspense → resolve path, the test needs a module that goes
 * through the real dynamic-import pipeline, not a stubbed
 * one. vitest + Vite handle `import()` on local source files
 * via the same transform pipeline used in production.
 *
 * The fixture lives in `__fixtures__/` so:
 *   (a) it's not picked up by the route module-graph glob
 *       (`src/routes/**`), which only globs under `src/routes/`;
 *   (b) it's clear in the test imports that this is fixture
 *       code, not production code.
 */

export function Greeter({ name }: { name: string }) {
  return (
    <div data-testid="greeter">hello {name}</div>
  );
}

export function AnotherComponent() {
  return <div data-testid="another">another</div>;
}

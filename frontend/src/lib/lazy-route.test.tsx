import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { Component, Suspense, type ReactNode } from "react";
import { lazyRoute } from "./lazy-route";

// Sprint 68 X-B1: vitest config has `globals: false` and does
// not auto-cleanup between tests. Project convention
// (per CockpitLayout.test.tsx, etc.) is explicit
// `afterEach(cleanup)`.
afterEach(() => {
  cleanup();
});

// Minimal ErrorBoundary for the "throws" test. Without it, a
// failing lazy component becomes an unhandled exception that
// vitest reports as a test failure even when the test asserts
// the throw. Sprint 62 pattern: class component is fine here
// because React ErrorBoundary requires it (no hook equivalent
// before React 19's `use` for error contexts).
class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return <div data-testid="error">{this.state.error.message}</div>;
    }
    return this.props.children;
  }
}

describe("lazyRoute", () => {
  it("returns a lazy component that renders the named export after the import resolves", async () => {
    const LazyGreeter = lazyRoute(
      () => import("./__fixtures__/lazy-fixture"),
      "Greeter",
    );

    render(
      <ErrorBoundary>
        <Suspense fallback={<div data-testid="fallback">loading</div>}>
          <LazyGreeter name="world" />
        </Suspense>
      </ErrorBoundary>,
    );

    // The real `import()` of a local fixture resolves within a
    // microtask, so we may go straight to the resolved state
    // before the assertion. Use waitFor either way to handle
    // the async resolution.
    await waitFor(() => {
      expect(screen.getByTestId("greeter")).toHaveTextContent("hello world");
    });
  });

  it("throws if the named export is missing", async () => {
    const LazyMissing = lazyRoute(
      () => import("./__fixtures__/lazy-fixture"),
      "DoesNotExist",
    );

    render(
      <ErrorBoundary>
        <Suspense fallback={<div data-testid="fallback">loading</div>}>
          <LazyMissing />
        </Suspense>
      </ErrorBoundary>,
    );

    // The ErrorBoundary should catch the rejected lazy import
    // and surface the helper's diagnostic message. This proves
    // (a) the missing-export check actually runs, and
    // (b) the message includes the export name + module keys
    //     for debuggability.
    await waitFor(() => {
      expect(screen.getByTestId("error")).toHaveTextContent(
        /lazyRoute.*DoesNotExist/,
      );
    });
  });
});

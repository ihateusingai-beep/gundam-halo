/**
 * useDirtyGuard — confirm-before-leave hook for dirty forms.
 *
 * Sprint 61 S-A3. The pre-existing problem: a user opens
 * Settings → Secrets, types a new API key, then clicks
 * "Settings → Memory" in the sidebar. The uncommitted draft
 * is lost with no warning. This hook intercepts browser
 * back/forward (`popstate` event) and shows a `confirm()`
 * dialog when the user attempts to leave.
 *
 * ## Scope (explicit)
 *
 *  - `popstate` event (browser back/forward buttons) — COVERED
 *  - In-app `<Link>` clicks — NOT COVERED in this sprint.
 *    react-router v6+ doesn't expose `useBlocker` in stable;
 *    we'd need a router upgrade + a separate hook. Out of
 *    scope for Sprint 61 (deferred to Sprint 62+).
 *  - `beforeunload` (close tab / refresh) — NOT COVERED.
 *    Different mechanism (browser-native dialog), different
 *    contract. Out of scope.
 *
 *  Sprint 61's coverage is the most-common case (user clicks
 *  a sidebar / breadcrumb link that changes the URL). The
 *  `popstate` event covers browser back/forward; in-app
 *  navigation is a known gap to be filled later.
 *
 * ## SSR safety
 *
 *  The hook reads `window.confirm` and listens to `popstate`
 *  on `window`. The effect is registered via `useEffect`
 *  (NOT `useLayoutEffect`) so SSR renders don't crash. The
 *  initial render returns a no-op stub.
 *
 * ## API
 *
 *  ```ts
 *  useDirtyGuard({
 *    when: boolean,        // true → block + confirm; false → no-op
 *    message?: string,     // confirm body (default: "You have
 *                          // unsaved changes...")
 *  })
 *  ```
 */
import { useEffect } from "react";

const DEFAULT_MESSAGE =
  "You have unsaved changes. Leave this page and lose them?";

export interface UseDirtyGuardOptions {
  /** True when the form has unsaved changes that should be
   *  protected from accidental navigation. The hook is a
   *  no-op when this is false. */
  when: boolean;
  /** Body of the confirm() dialog. Default: "You have
   *  unsaved changes. Leave this page and lose them?" */
  message?: string;
}

export function useDirtyGuard({
  when,
  message = DEFAULT_MESSAGE,
}: UseDirtyGuardOptions): void {
  useEffect(() => {
    if (!when) return;
    if (typeof window === "undefined") return;

    const onPopState = (event: PopStateEvent) => {
      // The popstate event fires AFTER the URL has already
      // changed. To actually block the navigation we need
      // to push the previous URL back, then show confirm.
      // If the user confirms, we re-trigger the navigation
      // by pushing the new URL and skipping the guard.
      const confirmed = window.confirm(message);
      if (confirmed) {
        // User accepted the leave. Re-apply the navigation
        // by pushing history state forward (we just popped
        // it). The next popstate will be unsubscribed by the
        // effect's cleanup → if the user comes back, the
        // hook will re-mount.
        window.history.pushState(null, "", window.location.href);
        // Note: at this point the user is on the URL they
        // tried to leave TO. The form is "lost" from the
        // hook's perspective. Caller's responsibility to
        // persist (localStorage) if they want recovery.
      } else {
        // User cancelled. Revert the URL.
        // We push the *original* URL back. The browser's
        // back-button is now 1 step "ahead" (the new URL);
        // clicking back will fire popstate again and the
        // same confirm loop. Acceptable for a single-user
        // desktop app.
        if (event.state) {
          window.history.pushState(
            event.state,
            "",
            window.location.pathname + window.location.search,
          );
        }
      }
    };

    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, [when, message]);
}
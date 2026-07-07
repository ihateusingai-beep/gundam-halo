/**
 * Backend error classifier.
 *
 * Sprint 49 B5 — surface WHY a backend call failed, not just
 * THAT it failed. Every per-card `catch (e) => toast.error(...)`
 * should go through `classifyBackendError` and the matching
 * `backendErrorMessage` / `backendErrorAction` helpers so the
 * user gets:
 *
 *   - A specific error message (auth missing vs auth invalid
 *     vs backend down vs network)
 *   - A specific remediation action (run generate-auth-token.sh,
 *     restart backend, open docs)
 *
 * The classifier is pure — `classifyBackendError(e: unknown)`
 * returns a `BackendErrorKind` enum. The toast action and
 * message helpers map that to user-facing strings.
 */
import { ApiError } from "./api";

/** Coarse error classification. Add new kinds only when the
 *  user can act on them differently. */
export type BackendErrorKind =
  | "auth-missing"
  | "auth-invalid"
  | "backend-down"
  | "backend-error"
  | "rate-limited"
  | "validation"
  | "not-found"
  | "timeout"
  | "unknown";

/** Classify any error thrown by the API client.
 *
 *  Mapping (per `app/core/auth.py` and FastAPI defaults):
 *   - 401 → "auth-invalid" (token wrong, .env mismatch)
 *   - 403 → "auth-invalid" (token lacks permission; rare in single-user)
 *   - 404 → "not-found"
 *   - 422 → "validation" (FastAPI Pydantic validation; usually
 *     means the request body was malformed — show server message)
 *   - 429 → "rate-limited" (LLM provider rate limit)
 *   - 500 → "backend-error" (Python exception, log check)
 *   - 502/504 → "backend-down" (gateway / upstream timeout)
 *   - **503 → "auth-missing"** — `app/core/auth.py` returns 503 when
 *     `HALO_API_TOKEN` env is unset. Surface as "auth-missing"
 *     because the remediation (run `generate-auth-token.sh`) is
 *     specific to that condition, not a generic "service
 *     unavailable" message.
 *   - `TypeError` (fetch network error) → "backend-down"
 *   - `DOMException` name === "AbortError" → "timeout" (the
 *     cockpit's 5s health-check timeout triggers this)
 *   - everything else → "unknown"
 */
export function classifyBackendError(e: unknown): BackendErrorKind {
  if (e instanceof ApiError) {
    if (e.status === 401 || e.status === 403) return "auth-invalid";
    if (e.status === 404) return "not-found";
    if (e.status === 422) return "validation";
    if (e.status === 429) return "rate-limited";
    if (e.status === 500) return "backend-error";
    // 503 means "auth token not configured" in this app
    // (see `app/core/auth.py:289`). 502/504 are upstream
    // gateway timeouts — those are "backend-down".
    if (e.status === 503) return "auth-missing";
    if (e.status === 502 || e.status === 504) return "backend-down";
    // Fallthrough for ApiError with unexpected status codes
    return "unknown";
  }
  if (e instanceof TypeError) {
    // fetch failed entirely — DNS, connection refused, CORS, etc.
    return "backend-down";
  }
  if (
    typeof e === "object" &&
    e !== null &&
    (e as { name?: string }).name === "AbortError"
  ) {
    return "timeout";
  }
  return "unknown";
}

/** Human-readable error message — split into 2 layers:
 *   1. `headline` — what just happened (one short line)
 *   2. `hint` — what to do about it (one short line)
 *
 *  The previous implementation mixed "Server said: <detail>" with
 *  the actionable hint in a single string, so when a server
 *  message was present, the user got the server's text but
 *  lost the actionable hint. The two-line shape is the standard
 *  for `toast.error({ title, description })` and `<OfflineBanner>`.
 */
export function backendErrorMessage(
  kind: BackendErrorKind,
  err: unknown,
  serverMessage?: string,
): { headline: string; hint: string; detail?: string } {
  const detail =
    serverMessage ??
    (err instanceof ApiError
      ? extractDetail(err.body)
      : err instanceof Error
        ? err.message
        : String(err));
  const trimmedDetail =
    detail && typeof detail === "string" && detail.trim().length > 0
      ? detail.trim()
      : undefined;
  switch (kind) {
    case "auth-missing":
      return {
        headline: "Backend is not configured for auth.",
        hint: "Run `scripts/generate-auth-token.sh` to create $HALO_HOME/.env with HALO_API_TOKEN, then restart the backend.",
      };
    case "auth-invalid":
      return {
        headline: "Bearer token rejected by the backend.",
        hint: "Check that the backend and Tauri shell are reading the same $HALO_HOME/.env.",
        detail: trimmedDetail,
      };
    case "backend-down":
      return {
        headline: "Backend unreachable.",
        hint: "Is the backend running? Try `lsof -nP -iTCP:8765 -sTCP:LISTEN` and restart if needed.",
        detail: trimmedDetail,
      };
    case "backend-error":
      return {
        headline: "Backend crashed.",
        hint: "Check $HALO_HOME/logs/backend.log for the traceback.",
        detail: trimmedDetail,
      };
    case "rate-limited":
      return {
        headline: "LLM provider rate limit.",
        hint: "Wait a few seconds and retry.",
        detail: trimmedDetail,
      };
    case "validation":
      return {
        headline: "Request was rejected.",
        hint: "The form has invalid fields. See the server message below.",
        detail: trimmedDetail,
      };
    case "not-found":
      return {
        headline: "Resource not found.",
        hint: "It may have been deleted or never existed.",
        detail: trimmedDetail,
      };
    case "timeout":
      return {
        headline: "Request timed out (5 s).",
        hint: "The backend is slow or unresponsive. Try `pkill -f 'uvicorn app.main:halo_app'` and restart.",
      };
    case "unknown":
    default:
      return {
        headline: "Unknown error.",
        hint: "Check $HALO_HOME/logs/backend.log.",
        detail: trimmedDetail,
      };
  }
}

/** Optional remediation action for the toast. The caller can
 *  attach this to `toast.error({ action: { label, onClick } })`.
 *  Returns null if the kind has no actionable remediation.
 */
export function backendErrorAction(
  kind: BackendErrorKind,
): { label: string; onClick: () => void } | null {
  if (typeof window === "undefined") return null;
  switch (kind) {
    case "auth-missing":
    case "auth-invalid":
      return {
        label: "Open docs",
        onClick: () =>
          window.open(
            "/docs/SECURITY-HARDENING.md#dev-workflow-halo_test_auth_bypass",
            "_blank",
          ),
      };
    case "backend-down":
      return {
        label: "Open docs",
        onClick: () =>
          window.open(
            "/docs/TROUBLESHOOTING.md#backend-not-listening",
            "_blank",
          ),
      };
    case "backend-error":
      return {
        label: "Open logs",
        onClick: () =>
          window.open(
            "file://$HALO_HOME/logs/backend.log",
            "_blank",
          ),
      };
    default:
      return null;
  }
}

/** Extract `detail` from a FastAPI error body. FastAPI shapes
 *  errors as `{detail: string | object[]}`. Returning the
 *  string (or the first validation error's `msg` if the detail
 *  is an array) gives a single short message for the toast. */
function extractDetail(body: unknown): string | undefined {
  if (!body || typeof body !== "object") return undefined;
  const detail = (body as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string; loc?: string[] };
    const where = Array.isArray(first.loc)
      ? first.loc.filter((p) => p !== "body").join(".")
      : "";
    return where ? `${where}: ${first.msg ?? "validation error"}` : first.msg;
  }
  return undefined;
}

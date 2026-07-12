import { Routes, Route } from "react-router";
import { Suspense } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { CockpitLayout } from "@/components/layout/CockpitLayout";
import { MobileLayout } from "@/components/layout/MobileLayout";
import { RouteFallback } from "@/components/layout/RouteFallback";
import { OverviewPage } from "@/routes/index";
import { NewProjectPage } from "@/routes/projects/new";
import { ProjectDetailPage } from "@/routes/projects/[id]";
import { ProjectMemoryPage } from "@/routes/projects/[id]/memory";
import { SessionDetailPage } from "@/routes/projects/[id]/sessions/[sessionId]";
import { SettingsPage } from "@/routes/settings";
import { SetupPage } from "@/routes/setup";
import { ThemeSwitcher } from "@/components/gundam/ThemeSwitcher";
import { CommandPalette } from "@/components/gundam/CommandPalette";
import { HaloLive2DProvider } from "@/context/live2d-bridge-context";
import { lazyRoute } from "@/lib/lazy-route";
import { useResponsive } from "@/lib/use-responsive";

// Sprint 68 X-B1: code-split 783KB initial bundle. Lazy-load
// the 2 lowest-risk routes via `lazyRoute()` + per-route
// `<Suspense>`. The remaining 5 routes (Settings, Setup, the 3
// project routes) stay eager for now — defer to Sprint 68.5
// after this pilot proves the pattern.
//
// `lazyRoute()` wraps `React.lazy()` with named-export support
// (the route module-graph test convention from Sprint 60 uses
// `export function FooPage()` not `export default`). See
// `lib/lazy-route.tsx` for the full rationale.
const AuditDashboardPage = lazyRoute(
  () => import("@/routes/audit"),
  "AuditDashboardPage",
);
const NotFoundPage = lazyRoute(
  () => import("@/routes/NotFound"),
  "NotFoundPage",
);

/**
 * Single source of truth for the route map. Previously the same `<Routes>`
 * block was duplicated for `isMobile` (MobileLayout) and desktop
 * (CockpitLayout) — a new route added to one side and not the other
 * would silently redirect mobile users to `/` (the catch-all). Extracting
 * this once means future route additions only need to touch one place.
 *
 * Sprint 61 R-A4: wrapped in `<QueryClientProvider>` so the audit
 * dashboard (and future TanStack Query adopters) can use `useQuery`
 * with shared cache. The single client is created once at module
 * load and lives for the lifetime of the app.
 */
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Audit log doesn't change mid-session — 30s staleTime
      // dedupes rapid remounts without serving stale data for
      // long. Window focus refetch gives the user a quick
      // refresh if they tab away + back.
      staleTime: 30_000,
      refetchOnWindowFocus: true,
      // Don't retry on 4xx — auth-missing / not-found won't
      // succeed on retry.
      retry: (failureCount, error) => {
        const status = (error as { status?: number })?.status;
        if (status && status >= 400 && status < 500) return false;
        return failureCount < 2;
      },
    },
  },
});

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/projects/new" element={<NewProjectPage />} />
      <Route path="/projects/:id" element={<ProjectDetailPage />} />
      <Route path="/projects/:id/memory" element={<ProjectMemoryPage />} />
      <Route
        path="/projects/:id/sessions/:sessionId"
        element={<SessionDetailPage />}
      />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="/setup" element={<SetupPage />} />
      {/* Sprint 68 X-B1: lazy route + per-route Suspense so the
          cockpit chrome stays mounted while the chunk loads. */}
      <Route
        path="/audit"
        element={
          <Suspense fallback={<RouteFallback />}>
            <AuditDashboardPage />
          </Suspense>
        }
      />
      {/* Sprint 60 R-A3: friendly 404 instead of silent redirect.
          The previous `<Navigate to="/" replace />` swallowed the
          user's typo with no feedback — they ended up on `/`
          wondering why their deep link didn't work. Sprint 68
          X-B1: also lazy-loaded — 404s are the lowest-traffic
          route, so this is the safest pilot candidate. */}
      <Route
        path="*"
        element={
          <Suspense fallback={<RouteFallback />}>
            <NotFoundPage />
          </Suspense>
        }
      />
    </Routes>
  );
}

export default function App() {
  const isMobile = useResponsive();

  return (
    <QueryClientProvider client={queryClient}>
      {/* Floating theme switcher (always visible) */}
      <ThemeSwitcher />

      <HaloLive2DProvider>
        {isMobile ? (
          <MobileLayout>
            <AppRoutes />
          </MobileLayout>
        ) : (
          <CockpitLayout>
            <AppRoutes />
          </CockpitLayout>
        )}
      </HaloLive2DProvider>

      {/* Global command palette — Cmd/Ctrl+K. Mounted last so it sits
          above all other UI. Self-contained: subscribes to its own
          open/close bus and reads the global Cmd/Ctrl+K shortcut. */}
      <CommandPalette />
    </QueryClientProvider>
  );
}

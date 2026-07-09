import { Routes, Route } from "react-router";

import { CockpitLayout } from "@/components/layout/CockpitLayout";
import { MobileLayout } from "@/components/layout/MobileLayout";
import { OverviewPage } from "@/routes/index";
import { NewProjectPage } from "@/routes/projects/new";
import { ProjectDetailPage } from "@/routes/projects/[id]";
import { ProjectMemoryPage } from "@/routes/projects/[id]/memory";
import { SessionDetailPage } from "@/routes/projects/[id]/sessions/[sessionId]";
import { SettingsPage } from "@/routes/settings";
import { SetupPage } from "@/routes/setup";
import { AuditDashboardPage } from "@/routes/audit";
import { NotFoundPage } from "@/routes/NotFound";
import { ThemeSwitcher } from "@/components/gundam/ThemeSwitcher";
import { CommandPalette } from "@/components/gundam/CommandPalette";
import { HaloLive2DProvider } from "@/context/live2d-bridge-context";
import { useResponsive } from "@/lib/use-responsive";

/**
 * Single source of truth for the route map. Previously the same `<Routes>`
 * block was duplicated for `isMobile` (MobileLayout) and desktop
 * (CockpitLayout) — a new route added to one side and not the other
 * would silently redirect mobile users to `/` (the catch-all). Extracting
 * this once means future route additions only need to touch one place.
 */
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
      <Route path="/audit" element={<AuditDashboardPage />} />
      {/* Sprint 60 R-A3: friendly 404 instead of silent redirect.
          The previous `<Navigate to="/" replace />` swallowed the
          user's typo with no feedback — they ended up on `/`
          wondering why their deep link didn't work. */}
      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  );
}

export default function App() {
  const isMobile = useResponsive();

  return (
    <>
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
    </>
  );
}

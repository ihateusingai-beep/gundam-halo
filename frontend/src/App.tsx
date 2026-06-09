import { Routes, Route, Navigate } from "react-router";

import { CockpitLayout } from "@/components/layout/CockpitLayout";
import { MobileLayout } from "@/components/layout/MobileLayout";
import { OverviewPage } from "@/routes/index";
import { CyberWaveformDemo } from "@/routes/cyber-wave-demo";
import { NewProjectPage } from "@/routes/projects/new";
import { ProjectDetailPage } from "@/routes/projects/[id]";
import { ProjectMemoryPage } from "@/routes/projects/[id]/memory";
import { SettingsPage } from "@/routes/settings";
import { ThemeSwitcher } from "@/components/gundam/ThemeSwitcher";
import { HaloLive2DProvider } from "@/context/live2d-bridge-context";
import { useResponsive } from "@/lib/use-responsive";

export default function App() {
  const isMobile = useResponsive();

  return (
    <>
      {/* Floating theme switcher (always visible) */}
      <ThemeSwitcher />

      <HaloLive2DProvider>
        {isMobile ? (
          <MobileLayout>
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/projects/new" element={<NewProjectPage />} />
              <Route path="/projects/:id" element={<ProjectDetailPage />} />
              <Route path="/projects/:id/memory" element={<ProjectMemoryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </MobileLayout>
        ) : (
          <CockpitLayout>
            <Routes>
              <Route path="/" element={<OverviewPage />} />
              <Route path="/projects/new" element={<NewProjectPage />} />
              <Route path="/projects/:id" element={<ProjectDetailPage />} />
              <Route path="/projects/:id/memory" element={<ProjectMemoryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="/cyber-wave-demo" element={<CyberWaveformDemo />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </CockpitLayout>
        )}
      </HaloLive2DProvider>
    </>
  );
}

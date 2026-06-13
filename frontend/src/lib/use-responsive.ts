/**
 * Responsive breakpoint hook.
 * Returns true if viewport is below the mobile breakpoint (768px).
 */

import { useEffect, useState } from "react";

const MOBILE_BREAKPOINT = 768;

export function useResponsive() {
  const [isMobile, setIsMobile] = useState(
    typeof window !== "undefined" && window.innerWidth < MOBILE_BREAKPOINT,
  );

  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < MOBILE_BREAKPOINT);
    window.addEventListener("resize", handler);
    return () => window.removeEventListener("resize", handler);
  }, []);

  return isMobile;
}

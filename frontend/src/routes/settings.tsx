// Re-export entry point — keeps the public import path stable
// (`@/routes/settings`) while the real orchestrator lives in
// `./settings/index.tsx` next to its per-tab siblings.
export { SettingsPage } from "./settings/index";

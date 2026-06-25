import { Link } from "react-router";

import { HudCard } from "@/components/gundam/HudCard";

/**
 * /setup — Sprint 39 stub.
 *
 * The full M13 first-run wizard lives in the backend
 * (`backend/app/api/setup.py` + `setup_state.py`).
 * This route is a placeholder so the SetupWizard card
 * on the home page has something to link to. The actual
 * wizard UI lands in a follow-up sprint — Sprint 40 will
 * fill in the step-by-step UI (theme picker → LLM
 * provider → wake phrases → voice backend → etc.).
 *
 * For now the page just shows the current setup state +
 * a friendly note pointing back to the home page.
 */

export function SetupPage() {
  return (
    <div className="max-w-2xl mx-auto p-4 space-y-4">
      <header>
        <h1 className="text-2xl font-[Orbitron] text-[var(--accent)] uppercase tracking-widest">
          Setup Wizard
        </h1>
        <p className="text-xs text-[var(--text-muted)] font-mono mt-1">
          First-run configuration — theme, LLM provider, voice pipeline.
        </p>
      </header>

      <HudCard>
        <div data-testid="setup-page-stub" className="space-y-2">
          <p className="text-sm text-[var(--text-primary)]">
            The wizard UI lands in Sprint 40. The backend is ready:
          </p>
          <ul className="text-xs font-mono text-[var(--text-secondary)] space-y-1 list-disc list-inside">
            <li>8 setup steps wired in <code>app/core/setup_state.py</code></li>
            <li>
              REST surface at <code>/api/setup/state</code> + 7 other endpoints
            </li>
            <li>Persists progress to <code>~/.gundam-halo/setup_state.json</code></li>
          </ul>
          <p className="text-[10px] text-[var(--text-muted)] font-mono mt-3">
            For now, the home page card links here. Use{" "}
            <code>~/.gundam-halo/config.toml</code> directly to configure before
            the wizard UI ships.
          </p>
          <Link
            to="/"
            className="inline-block mt-3 text-[10px] font-[Rajdhani] uppercase tracking-wider text-[var(--accent)] hover:text-[var(--text-primary)] transition-colors"
          >
            ← Back to cockpit
          </Link>
        </div>
      </HudCard>
    </div>
  );
}

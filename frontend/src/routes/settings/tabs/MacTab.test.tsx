/**
 * MacTab.test.tsx — Sprint 72 X-A1g.
 *
 * Unit test for the Mac settings tab. MacTab takes a
 * `settings` prop (no async fetch), so this is a pure
 * render test. Aims to bump `MacTab.tsx` coverage from
 * 0% to ~95% (Sprint 72 X-A1g coverage ratchet; target:
 * line coverage ≥60%).
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { MacTab } from "./MacTab";
import type { Settings } from "@/types/api";

const TEST_SETTINGS: Settings = {
  mac: {
    default_path_policy: "project_only",
    file_read_paths: ["~/projects/**", "/tmp/**"],
    file_write_paths: ["~/projects/output/**"],
    shell_allowlist: ["ls", "cat", "grep"],
    apple_script_enabled: true,
    notifications_enabled: true,
    a11y_enabled: false,
  },
};

afterEach(() => {
  cleanup();
});

describe("MacTab", () => {
  it("renders the 3 sections (Path Policy, Shell Allowlist, Capabilities)", () => {
    render(<MacTab settings={TEST_SETTINGS} />);
    expect(screen.getByText(/Path Policy/i)).toBeInTheDocument();
    expect(screen.getByText(/Shell Allowlist/i)).toBeInTheDocument();
    expect(screen.getByText(/Capabilities/i)).toBeInTheDocument();
  });

  it("renders the path policy values (default mode + path lists)", () => {
    render(<MacTab settings={TEST_SETTINGS} />);
    // `project_only` appears in both the value span and the
    // hint span — use getAllByText to assert both.
    expect(screen.getAllByText(/project_only/i).length).toBeGreaterThanOrEqual(1);
    // The 2 file read paths + 1 file write path should be rendered.
    // PathList renders each path in a <li>.
    expect(screen.getByText(/~\/projects\/\*\*/)).toBeInTheDocument();
    expect(screen.getByText(/\/tmp\/\*\*/)).toBeInTheDocument();
    expect(screen.getByText(/~\/projects\/output\/\*\*/)).toBeInTheDocument();
  });

  it("renders the shell allowlist as a list of span chips", () => {
    render(<MacTab settings={TEST_SETTINGS} />);
    // The 3 shell commands should each render as a <span>.
    expect(screen.getByText("ls")).toBeInTheDocument();
    expect(screen.getByText("cat")).toBeInTheDocument();
    expect(screen.getByText("grep")).toBeInTheDocument();
  });

  it("renders the capability toggles (AppleScript + Notifications + Accessibility)", () => {
    render(<MacTab settings={TEST_SETTINGS} />);
    // "AppleScript" and "Notifications" might appear in multiple
    // elements (label + hint). Use getAllByText to assert presence.
    expect(screen.getAllByText(/AppleScript/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Notifications/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Accessibility/i).length).toBeGreaterThanOrEqual(1);
  });
});
